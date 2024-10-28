import time 
import redis 
import os 
import json 
from .debug_print import debug_print

class ThrottledEmit:
    def __init__(self, sio, event:str, rate_s:float=1, room=None) -> None:
        self.m_sio = sio 
        self.m_event = event 
        self.m_rate_s = rate_s 
        self.m_room = room 
        self.m_last_emit_time = None  

    def _emit(self, msg):
        self.m_sio.emit(self.m_event, msg, to=self.m_room)
        self.m_last_emit_time = time.time()

    def emit(self, msg):
        if self.m_last_emit_time is None :
            debug_print(msg)
            self._emit(msg)
            return 
        
        current_time = time.time()
        if current_time - self.m_last_emit_time > self.m_rate_s:
            self._emit(msg)
            debug_print(msg)

            
    def close(self):
        self._emit("")

class RedisThrottledEmit:
    def __init__(self, event:str, rate_s:float=1, room=None) -> None:
        redis_host = os.environ.get("REDIS_HOST", "localhost")
        self.redis = redis.StrictRedis(host=redis_host, port=6379, db=0)

        self.m_event = event 
        self.m_rate_s = rate_s 
        self.m_room = room 
        self.m_last_emit_time = None  
    
    def _redis_emit(self, event:str, msg:any, to=None):
        data = {
            "event": event,
            "msg": msg
            }
        if to is not None:
            data["to"] = to

        self.redis.lpush("emit", json.dumps(data))

    def _emit(self, msg):
        self._redis_emit(self.m_event, msg, to=self.m_room)
        self.m_last_emit_time = time.time()

    def emit(self, msg):
        if self.m_last_emit_time is None :
            debug_print(msg)
            self._emit(msg)
            return 
        
        current_time = time.time()
        if current_time - self.m_last_emit_time > self.m_rate_s:
            self._emit(msg)
            debug_print(msg)

            
    def close(self):
        self._emit("")
