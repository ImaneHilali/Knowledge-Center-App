# tasks.py
from celery import shared_task

from search.models import File
from search.utils import summarize_content_with_bart
import logging

logger = logging.getLogger(__name__)


@shared_task
def generate_summary_and_save(file_id):
    try:
        logger.info(f"Task started for file ID: {file_id}")
        file_instance = File.objects.get(id=file_id)

        text_content = file_instance.content
        logger.info(f"Retrieved content for file ID: {file_id}")

        summary = summarize_content_with_bart(text_content)
        logger.info(f"Generated summary for file ID: {file_id}: {summary}")

        # Log the generated summary
        print(f"Generated summary for file {file_id}: {summary}")

        # Save summary to file instance
        file_instance.summary = summary(file_id=file_id)
        file_instance.save()
        logger.info(f"Successfully saved summary for file ID: {file_id}")

        # Log the successful save operation
        print(f"Successfully saved summary for file {file_id}")

    except File.DoesNotExist:
        print(f"File with ID {file_id} does not exist")
        logger.error(f"File with ID {file_id} does not exist")

    except Exception as e:
        print(f"An error occurred while processing file {file_id}: {e}")
        logger.error(f"An error occurred while processing file {file_id}: {e}")
