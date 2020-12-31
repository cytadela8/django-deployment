from decorator import decorator
import sys
import invoke.exceptions

from logger import logger


EXTERNAL_EXCEPTIONS = (invoke.exceptions.UnexpectedExit, AssertionError)


class Fallback(Exception):
    """
    Fallback exception is thrown by an function when it fails to perform it's
    action, but leaves the host unchanged (succeeds in removing all of it's
    effects)
    """
    def __init__(self, original_exception):
        super().__init__("Fallback executed successfully.")
        self.original_exception = original_exception


@decorator
def handle_exceptions(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except Fallback as e:
        logger.warning("Script finished with Fallback. Original Error:")
        logger.exception(e.original_exception)
        logger.warning("Script finished with Fallback.")
        if not isinstance(e.original_exception, EXTERNAL_EXCEPTIONS):
            logger.error("Exception type suggests internal deployment script "
                         "error!")
            sys.exit(99)
        else:
            sys.exit(1)
    except EXTERNAL_EXCEPTIONS as e:
        logger.error("Scripted finished with unhandled external error:")
        logger.exception(e)
        logger.error("Scripted finished with unhandled external error!")
        sys.exit(101)
    except Exception as e:
        logger.error("Scripted finished with unhandled internal Exception:")
        logger.exception(e)
        logger.error("Scripted finished with unhandled internal Exception!")
        sys.exit(199)
