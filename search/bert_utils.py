# search/utils.py
import string
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
import tika
from transformers import BertTokenizer, BertModel


STOPWORDS_LANGUAGE = 'english'
MAX_TOKEN_LENGTH = 512

# Download NLTK resources
nltk.download('punkt')
nltk.download('stopwords')

# Initialize Tika
tika.initVM()


# Load BERT tokenizer and model
tokenizer = BertTokenizer.from_pretrained('bert-base-uncased')
model = BertModel.from_pretrained('bert-base-uncased')


def preprocess_text(text):
    """Preprocess the given text by tokenizing, removing punctuation, and stop words."""
    tokens = word_tokenize(text)
    tokens = [word for word in tokens if word not in string.punctuation]
    stop_words = set(stopwords.words(STOPWORDS_LANGUAGE))
    tokens = [word for word in tokens if word.lower() not in stop_words]
    return ' '.join(tokens)



