from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from .bert_utils import preprocess_text, tokenizer, model, MAX_TOKEN_LENGTH
import torch


class File(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    path = models.CharField(max_length=255)
    content = models.TextField()
    embedding = models.BinaryField()
    summary = models.TextField()
    upload_date = models.DateTimeField(default=timezone.now)
    preview_url = models.CharField(max_length=1024, blank=True)

    @classmethod
    def insert_file_to_db(cls, user, name, path, content, summary, preview_url):
        preprocessed_text = preprocess_text(content)

        # Calculate BERT embeddings for the document
        document_tokens = tokenizer.encode(preprocessed_text, add_special_tokens=True, max_length=MAX_TOKEN_LENGTH,
                                           truncation=True, padding='max_length', return_tensors='pt')
        with torch.no_grad():
            outputs = model(document_tokens)
            embeddings = outputs.last_hidden_state[:, 0, :].numpy()

        # Convert embeddings to bytes for storage in the database
        embeddings_blob = embeddings.tobytes()

        try:
            file = cls.objects.create(user=user, name=name, path=path, content=content, embedding=embeddings_blob, summary=summary, upload_date=timezone.now(), preview_url=preview_url)
            return file
        except Exception as e:
            print(f"Error inserting file '{name}' into the database: {e}")
            return None

    @classmethod
    def retrieve_files_from_db(cls):
        """Retrieve files data from the database."""
        files = cls.objects.all().values('id', 'user__username', 'name', 'path', 'content', 'embedding', 'summary', 'upload_date', 'preview_url')
        return files
