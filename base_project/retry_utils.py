import logging
import random
import time
from functools import wraps

logger = logging.getLogger(__name__)


def retry_with_backoff(
    initial_delay=0.1,
    max_delay=60,
    max_retries=5,
    backoff_factor=2,
    jitter=0.1,
    exceptions=(Exception,),
):
    """
    Decorator for retrying a function with exponential backoff.

    Args:
        initial_delay (float): Initial delay between retries in seconds
        max_delay (float): Maximum delay between retries in seconds
        max_retries (int): Maximum number of retries
        backoff_factor (float): Backoff multiplier (e.g. value of 2 will double the delay each retry)
        jitter (float): Jitter factor to add randomness to delay (0-1)
        exceptions (tuple): Exceptions to catch and retry on

    Returns:
        Decorated function with retry logic
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            delay = initial_delay

            while True:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    retries += 1
                    if retries > max_retries:
                        logger.error(f"Maximum retries ({max_retries}) exceeded for {func.__name__}: {str(e)}")
                        raise

                    # Calculate delay with jitter
                    jitter_amount = delay * jitter
                    actual_delay = delay + random.uniform(-jitter_amount, jitter_amount)
                    actual_delay = max(initial_delay, actual_delay)  # Don't go below initial delay

                    logger.warning(
                        f"Retry {retries}/{max_retries} for {func.__name__} after {actual_delay:.2f}s: {str(e)}"
                    )
                    time.sleep(actual_delay)

                    # Increase delay for next retry with exponential backoff
                    delay = min(max_delay, delay * backoff_factor)

        return wrapper

    return decorator


class RetryStrategy:
    """
    Configurable retry strategy with exponential backoff.
    """

    def __init__(
        self,
        initial_delay=0.1,
        max_delay=60,
        max_retries=5,
        backoff_factor=2,
        jitter=0.1,
    ):
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.jitter = jitter
        self.retry_count = 0
        self.current_delay = initial_delay
        self.last_exception = None
        self.last_attempt_time = 0

    def reset(self):
        """Reset the retry counter and delay."""
        self.retry_count = 0
        self.current_delay = self.initial_delay
        self.last_exception = None
        self.last_attempt_time = 0

    def next_delay(self):
        """
        Calculate the next delay interval with jitter.

        Returns:
            float: The next delay in seconds
        """
        if self.retry_count >= self.max_retries:
            return None

        jitter_amount = self.current_delay * self.jitter
        actual_delay = self.current_delay + random.uniform(-jitter_amount, jitter_amount)
        actual_delay = max(self.initial_delay, actual_delay)  # Don't go below initial delay

        # Increase delay for next retry
        self.current_delay = min(self.max_delay, self.current_delay * self.backoff_factor)
        self.retry_count += 1

        return actual_delay

    def execute(self, func, *args, **kwargs):
        """
        Execute a function with retry logic.

        Args:
            func: The function to execute
            *args: Arguments to pass to the function
            **kwargs: Keyword arguments to pass to the function

        Returns:
            The result of the function call

        Raises:
            Exception: The last exception caught after all retries have been exhausted
        """
        self.reset()
        last_exception = None

        while True:
            try:
                self.last_attempt_time = time.time()
                return func(*args, **kwargs)
            except Exception as e:
                self.last_exception = e
                last_exception = e
                delay = self.next_delay()

                if delay is None:
                    logger.error(f"Maximum retries ({self.max_retries}) exceeded: {str(e)}")
                    raise last_exception

                logger.warning(f"Retry {self.retry_count}/{self.max_retries} after {delay:.2f}s: {str(e)}")
                time.sleep(delay)
