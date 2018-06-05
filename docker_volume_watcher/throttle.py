from threading import Timer

import time
import base64


def throttle(mindelta, groupByArgIndex):
    def decorator(fn):
        def throttled(*args, **kwargs):
            argEncoded = args[groupByArgIndex].encode()
            key = "lastTimeExecuted_" + base64.b64encode(argEncoded).decode('ascii')

            def call_it():
                setattr(throttled, key, time.time())

                fn(*args, **kwargs)

            if hasattr(throttled, key):

                lasttime = getattr(throttled, key)

            else:  # just execute fction

                try:
                    throttled.t.cancel()
                except(AttributeError):
                    pass
                call_it()
                return throttled

            delta = time.time() - getattr(throttled, key)
            try:
                throttled.t.cancel()
            except(AttributeError):

                pass
            if delta > mindelta:
                call_it()
            else:
                timespot = mindelta - delta
                timespot = timespot
                throttled.t = Timer(timespot, call_it)
                throttled.t.start()

        return throttled

    return decorator
