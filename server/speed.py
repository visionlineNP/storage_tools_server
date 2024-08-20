import time
import humanfriendly


class FileSpeedEstimate:
    def __init__(self, file_size) -> None:
        self.file_size = file_size
        self.start_time = time.time()
        self.transfered_size = 0
        self.seconds_remaining = None
        self.cycle_start_time = self.start_time
        self.transfer_speed_bytes_per_second = 0
        self.update_time = self.start_time
        self.update_rate = 1
        self.phase_copied = 0

    def update_existing(self, amount):
        current_time = time.time()
        self.transfered_size += abs(amount)
        self.cycle_start_time = current_time

    def update(self, amount):
        current_time = time.time()
        self.phase_copied += amount
        self.transfered_size += amount

        if current_time > (self.update_rate + self.update_time):
            time_delta = current_time - self.update_time
            self.transfer_speed_bytes_per_second = (
                0.90 * float(self.phase_copied) / time_delta
            ) + (0.10 * self.transfer_speed_bytes_per_second)
            remaining_size = self.file_size - self.transfered_size
            self.seconds_remaining = (
                float(remaining_size) / self.transfer_speed_bytes_per_second
            )
            self.update_time = current_time
            self.phase_copied = 0

    def get_percentage(self):
        return (100 * self.transfered_size) / self.file_size

    def getText(self):
        if self.seconds_remaining is None:
            return "Estimating"
        duration = humanfriendly.format_timespan(int(self.seconds_remaining))
        speed = (
            humanfriendly.format_size(int(self.transfer_speed_bytes_per_second)) + "/S"
        )
        text = speed + ", " + duration + " remaining"
        return text

    def __repr__(self) -> str:
        return f"<FileSpeedEstimate: file_size: {self.file_size}, transfered_size: {self.transfered_size}, bps: {self.transfer_speed_bytes_per_second} >"
