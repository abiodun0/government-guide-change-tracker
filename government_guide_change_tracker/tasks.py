from celery import shared_task


@shared_task
def example_task(message):
    """
    Example Celery task for testing.
    Usage: example_task.delay("Hello, Celery!")
    """
    print(f"Task received: {message}")
    return f"Processed: {message}"

