#!/usr/bin/env python
# Standard Python libraries.
import argparse
import json
import multiprocessing
import os
import queue
import sys
import threading
import time

# Third party Python libraries.


# Custom Python libraries.
import modules.api
import modules.logger
import modules.scanner


class Worker(threading.Thread):
    """Worker thread"""

    def __init__(self):
        """Initialize Worker thread."""

        threading.Thread.__init__(self)

    def run(self):
        """Start Worker thread."""

        while True:
            # Grab scan_job_dict off the queue.
            scan_job_dict = agent.queue.get()

            try:
                # Kick off scan.
                scan_process = multiprocessing.Process(target=modules.scanner.scan_site, args=(scan_job_dict,))
                scan_process.start()

            except Exception as e:
                modules.logger.ROOT_LOGGER.error(f"Failed to start scan.  Exception: {e}")

            agent.queue.task_done()


class Agent:
    """Main Agent class"""

    def __init__(self, config_file):
        """Initialize Agent class"""

        self.config_file = config_file

        # Load configuration file.
        self.config_data = self.load_config(self.config_file)

        # Create queue.
        self.queue = queue.Queue()

    def load_config(self, config_file):
        """Load the agent_config.json file and return a JSON object."""

        if os.path.isfile(config_file):
            with open(config_file) as fh:
                json_data = json.loads(fh.read())
                return json_data

        else:
            modules.logger.ROOT_LOGGER.error(f"'{config_file}' does not exist or contains no data.")
            sys.exit(0)

    def go(self):
        """Start the scan agent."""

        # Assign log level.  See README.md for more information.
        modules.logger.ROOT_LOGGER.setLevel((6 - self.config_data["log_verbosity"]) * 10)

        # Kickoff the threadpool.
        for i in range(self.config_data["number_of_threads"]):
            thread = Worker()
            thread.daemon = True
            thread.start()

        modules.logger.ROOT_LOGGER.info(f"Starting scan agent: {self.config_data['scan_agent']}", exc_info=False)

        while True:
            try:
                # Retrieve any new scan jobs from master through API.
                scan_jobs = modules.api.check_for_scan_jobs(self.config_data)

                if scan_jobs:
                    for scan_job in scan_jobs:
                        modules.logger.ROOT_LOGGER.info(f"scan_job: {scan_job}")

                        # Create new dictionary that will contain scan_job and config_data information.
                        scan_job_dict = {}
                        scan_job_dict["scan_job"] = scan_job
                        scan_job_dict["config_data"] = self.config_data

                        # Place scan_job_dict on queue.
                        self.queue.put(scan_job_dict)

                        # Allow the jobs to execute before changing status.
                        time.sleep(5)

                        # Update scan_status from "pending" to "started".
                        update_info = {"scan_status": "started"}
                        modules.api.update_scan_information(self.config_data, scan_job, update_info)

                    self.queue.join()

                else:
                    modules.logger.ROOT_LOGGER.info(
                        f"No scan jobs found...checking back in {self.config_data['callback_interval_in_seconds']} seconds."
                    )
                    time.sleep(self.config_data["callback_interval_in_seconds"])

            except KeyboardInterrupt:
                break

        modules.logger.ROOT_LOGGER.critical("Stopping Scantron")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scantron scan agent")
    parser.add_argument(
        "-c",
        dest="config_file",
        action="store",
        required=False,
        default="agent_config.json",
        help="Configuration file.  Defaults to 'agent_config.json'",
    )
    args = parser.parse_args()

    config_file = args.config_file

    # Log level is controlled in agent_config.json and assigned after reading that file.
    # Setup file modules.logger.logging
    log_file_handler = modules.logger.logging.FileHandler(os.path.join("logs", "agent.log"))
    log_file_handler.setFormatter(modules.logger.LOG_FORMATTER)
    modules.logger.ROOT_LOGGER.addHandler(log_file_handler)

    # Setup console modules.logger.logging
    console_handler = modules.logger.logging.StreamHandler()
    console_handler.setFormatter(modules.logger.LOG_FORMATTER)
    modules.logger.ROOT_LOGGER.addHandler(console_handler)

    agent = Agent(config_file)
    agent.go()
