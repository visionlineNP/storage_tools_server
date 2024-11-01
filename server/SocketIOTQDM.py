import humanfriendly
import socketio.exceptions
from tqdm import tqdm
from .debug_print import debug_print

import time


class SocketIOTQDM(tqdm):
    def __init__(self, *args, **kwargs):
        self.room = kwargs.pop("room", None)
        self.event = kwargs.pop("event", "progress_update")
        self.sio = kwargs.pop("socket", None)
        self.source = kwargs.pop("source", None)
        self.position = kwargs.get("position", None)
        self.emit_interval = kwargs.get("emit_interval", 1)
        self.last_emit_time = time.time()
        self.debug = kwargs.get("debug", False)
        super().__init__(*args, **kwargs)

        if self.sio:
            msg = {
                "source": self.source,
                "desc": self.desc,
                "progress": self.n,
                "total": self.total,
                "position": self.position,
            }

            try:
                if self.room:
                    self.sio.emit(self.event, msg, room=self.room)
                else:
                    self.sio.emit(self.event, msg)
            except socketio.exceptions.BadNamespaceError:
                pass

    def _emit_update(self, msg):
        if not self.sio:
            return
        current_time = time.time()
        if current_time - self.last_emit_time > self.emit_interval:
            if self.room:
                self.sio.emit(self.event, msg, room=self.room, debug=self.debug)
            else:
                self.sio.emit(self.event, msg, debug=self.debug)
            self.last_emit_time = current_time

    def update(self, n=1):
        super().update(n)
        if not self.sio:
            return

        remaining = "Estimating"
        rate = self.format_dict["rate"]
        if rate:
            remaining = (self.total - self.n) / rate
            remaining = humanfriendly.format_timespan(remaining)
        else:
            rate = 0

        msg = {
            "source": self.source,
            "desc": self.desc,
            "progress": self.n,
            "total": self.total,
            "position": self.position,
            "rate": humanfriendly.format_size(rate) + "/S",
            "remaining": remaining,
        }

        try:
            self._emit_update(msg)
        except socketio.exceptions.BadNamespaceError:
            pass


    def close(self):
        super().close()

        msg = {
            "source": self.source,
            "desc": self.desc,
            "progress": -1,
            "total": self.total,
            "position": self.position,
        }
        try:
            if self.room:
                self.sio.emit(self.event, msg, to=self.room)
            else:
                self.sio.emit(self.event, msg)
        except socketio.exceptions.BadNamespaceError as e:
            # got disconnected.
            pass

class MultiTargetSocketIOTQDM(tqdm):  
    """
    A subclass of tqdm that emits progress updates to multiple Socket.IO targets. 

    Attributes:
        room (str): The Socket.IO room to emit updates to.
        sio_events (list): List of Socket.IO instances and events to emit.
        source (str): Identifier for the source of progress updates.
        position (int): Position indicator for the progress bar.
        emit_interval (float): Minimum interval between emitting progress updates.
        debug (bool): Flag for enabling debug mode in emissions.
    """

    def __init__(self, *args, **kwargs):
        """
        Initializes the progress bar with specified attributes and emits initial status.

        Args:
            *args: Positional arguments for tqdm initialization.
            **kwargs: Additional arguments, including 'room', 'socket_events', 'source', 'emit_interval', and 'debug'.
        """
        self.room = kwargs.pop('room', None)
        self.sio_events = kwargs.pop('socket_events', [])
        self.source = kwargs.pop('source', None)
        self.position = kwargs.get("position", None)
        self.emit_interval = kwargs.pop("emit_interval", 1)
        self.last_emit_time = time.time()
        self.debug = kwargs.pop("debug", False)
        super().__init__(*args, **kwargs)

        for (sio, event, room) in self.sio_events:
            msg = {
                "source": self.source,
                "desc": self.desc,
                "progress": self.n,
                "total": self.total,
                "position": self.position
            }

            try:
                self._emit_message(msg, sio, event, room)
            except socketio.exceptions.BadNamespaceError:
                pass

    def _emit_update(self, msg):
        """
        Emits a progress update to all specified Socket.IO events, if the emit interval has passed.

        Args:
            msg (dict): Message data to be emitted.
        """
        if len(self.sio_events) == 0:
            return 

        current_time = time.time()
        if current_time - self.last_emit_time > self.emit_interval:
            for sio, event, room in self.sio_events:

                self._emit_message(msg, sio, event, room)
            self.last_emit_time = current_time

    def _emit_message(self, msg, sio, event, room):
        """
        Emits a specific message to a Socket.IO event, with an optional room target.

        Args:
            msg (dict): Message data to emit.
            sio: Socket.IO instance.
            event (str): Event name to emit to.
            room (str or None): Optional room to target.
        """
        if room:
            sio.emit(event, msg, to=room, debug=self.debug)
        else:
            sio.emit(event, msg, debug=self.debug)
        

    def update(self, n=1):
        """
        Updates the progress bar by `n` steps and emits progress status if needed.

        Args:
            n (int): Number of steps to advance the progress bar.
        """
        super().update(n)

        if len(self.sio_events) == 0:
            return 
        
        remaining = "Estimating"
        rate = self.format_dict["rate"]
        if rate:
            remaining = (self.total - self.n) / rate
            remaining = humanfriendly.format_timespan(remaining)
        else:
            rate = 0

        if self.unit == "B":
            hrate = humanfriendly.format_size(rate) + "/S"
        else:
            hrate = humanfriendly.format_number(rate) + " it/S"

        msg = {
            "source": self.source,
            "desc": self.desc,
            "progress": self.n,
            "total": self.total,
            "position": self.position,
            "rate": hrate,
            "remaining": remaining
        }

        try:
            self._emit_update(msg)
        except socketio.exceptions.BadNamespaceError:
            pass

    def close(self):
        """
        Closes the progress bar and emits a final update with progress set to -1.
        """
        super().close()

        if len(self.sio_events) == 0:
            return 

        msg = {
            "source": self.source,
            "desc": self.desc,
            "progress": -1,
            "total": self.total,
            "position": self.position,
        }

        for sio, event, room in self.sio_events:
            self._emit_message(msg, sio, event, room)


