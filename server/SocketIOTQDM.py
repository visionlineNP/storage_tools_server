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
                self.sio.emit(self.event, msg, debug_print=self.debug)
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
                self.sio.emit(self.event, msg, room=self.room)
            else:
                self.sio.emit(self.event, msg)
        except socketio.exceptions.BadNamespaceError as e:
            # got disconnected.
            pass

class MultiTargetSocketIOTQDM(tqdm):    
    def __init__(self, *args, **kwargs):
        self.room = kwargs.pop('room', None)
        # self.event = kwargs.pop('event', 'progress_update')
        self.sio_events = kwargs.pop('socket_events', [])
        self.source = kwargs.pop('source', None)
        self.position = kwargs.get("position", None)
        self.emit_interval = kwargs.pop("emit_interval", 1)
        self.last_emit_time = time.time()
        self.debug = kwargs.pop("debug", False)
        super().__init__(*args, **kwargs)

        # debug_print(self.sio_events)

        for (sio, event, room) in self.sio_events:
            msg = {
                "source": self.source,
                "desc": self.desc,
                "progress": self.n,
                "total": self.total,
                "position": self.position
            }

            try:
                if self.room:
                    sio.emit(event, msg, room=self.room, debug=self.debug)
                else:
                    sio.emit(event, msg, debug=self.debug)
            except socketio.exceptions.BadNamespaceError:
                pass

    def _emit_update(self, msg):

        if len(self.sio_events) == 0:
            return 

        current_time = time.time()
        if current_time - self.last_emit_time > self.emit_interval:

            for sio, event, room in self.sio_events:
                # debug_print((sio, event, room))
                if room:
                    sio.emit(event, msg, room=self.room, debug=self.debug)
                else:
                    sio.emit(event, msg, debug=self.debug)
            self.last_emit_time = current_time

    def update(self, n=1):
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
            try:
                if room:
                    sio.emit(event, msg, room=self.room)
                else:
                    sio.emit(event, msg)
            except socketio.exceptions.BadNamespaceError as e:
                # got disconnected.  
                pass

