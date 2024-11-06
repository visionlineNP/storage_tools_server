import json 
import os 
import redis 
import time 

from server.debug_print import debug_print


class RedisThrottledEmit:
    """
    A class to handle rate-limited event emissions using Redis.

    This class is used to emit messages to a Redis list at a throttled rate. It ensures that events are not emitted
    more frequently than a specified rate. Useful for reducing the number of messages sent in real-time systems.

    Environment:
        REDIS_HOST: default "localhost"

    Attributes:
        m_event (str): The event name to emit.
        m_rate_s (float): The minimum interval (in seconds) between successive emits.
        m_room (str, optional): The room identifier to which the event should be sent.
        m_last_emit_time (float, optional): The time of the last successful emit.
    """
    def __init__(self, event: str, rate_s: float = 1, room: str = None) -> None:
        """
        Initializes a RedisThrottledEmit instance.

        Args:
            event (str): The name of the event to be emitted.
            rate_s (float, optional): The rate limit for emitting messages, in seconds. Default is 1 second.
            room (str, optional): The room to which the event should be emitted. Default is None.
        """
        redis_host = os.environ.get("REDIS_HOST", "localhost")
        self.redis = redis.StrictRedis(host=redis_host, port=6379, db=0)

        self.m_event = event 
        self.m_rate_s = rate_s 
        self.m_room = room 
        self.m_last_emit_time = None  
    
    def _redis_emit(self, event: str, msg: any, to=None):
        """
        Emits a message to Redis.

        Args:
            event (str): The event name to emit.
            msg (any): The message content to emit.
            to (str, optional): The target room for the message. Default is None.
        """
        data = {
            "event": event,
            "msg": msg
        }
        if to is not None:
            data["to"] = to

        self.redis.lpush("emit", json.dumps(data))

    def _emit(self, msg):
        """
        Emits the current event with the given message.

        Args:
            msg (any): The message content to emit.
        """
        self._redis_emit(self.m_event, msg, to=self.m_room)
        self.m_last_emit_time = time.time()

    def emit(self, msg):
        """
        Emits the message if the rate limit allows it.

        Args:
            msg (any): The message content to emit.
        """
        if self.m_last_emit_time is None:
            debug_print(msg)
            self._emit(msg)
            return 
        
        current_time = time.time()
        if current_time - self.m_last_emit_time > self.m_rate_s:
            self._emit(msg)
            debug_print(msg)
            
    def close(self):
        """
        Closes the emitter by emitting an empty message to signal closure.
        """
        self._emit("")
