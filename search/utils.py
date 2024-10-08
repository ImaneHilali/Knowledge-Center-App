# search/utils.py
import re
import string
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
import tika
from tika import parser
from transformers import pipeline, BartTokenizer
from transformers import BertTokenizer, BertModel
from sklearn.metrics.pairwise import cosine_similarity
import torch
import numpy as np
from .models import File
from nltk.stem import WordNetLemmatizer


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

    # Remove excessive spaces and unnecessary line breaks
    text = re.sub(r'\s+', ' ', text).strip()

    tokens = word_tokenize(text)
    tokens = [word for word in tokens if word not in string.punctuation]
    stop_words = set(stopwords.words(STOPWORDS_LANGUAGE))
    tokens = [word for word in tokens if word.lower() not in stop_words]

    # Lemmatize tokens
    lemmatizer = WordNetLemmatizer()
    tokens = [lemmatizer.lemmatize(word.lower()) for word in tokens]

    return ' '.join(tokens)


def remove_space(text):
    # Remove excessive spaces and unnecessary line breaks
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def convert_to_txt(input_file_path):
    try:
        parsed_content = parser.from_file(input_file_path)
        text_content = parsed_content.get('content', '')
        preprocessed_text = remove_space(text_content)
        return preprocessed_text
    except Exception as e:
        print(f"Error converting file '{input_file_path}' to TXT: {e}")
        return None


def summarize_content_with_bart(content):
    # Initialize the summarization pipeline and tokenizer
    summarization_pipeline = pipeline("summarization", model="facebook/bart-large-cnn")
    tokenizer = BartTokenizer.from_pretrained("facebook/bart-large-cnn")
    max_input_length = 1024  # BART model's max input length in tokens

    # Tokenize the content and split into chunks that fit within the max token limit
    tokens = tokenizer(content, return_tensors='pt', truncation=False)['input_ids'][0]
    num_tokens = len(tokens)
    chunk_size = max_input_length - 2  # Allow space for special tokens

    # Create chunks of tokens
    chunks = [tokens[i:i + chunk_size] for i in range(0, num_tokens, chunk_size)]

    summaries = []
    for chunk in chunks:
        try:
            # Convert token chunk back to string
            chunk_text = tokenizer.decode(chunk, skip_special_tokens=True)
            # Summarize the chunk
            summary_chunk = summarization_pipeline(chunk_text, max_length=max_input_length, min_length=40, do_sample=False)[0]['summary_text']
            summaries.append(summary_chunk)
        except Exception as e:
            print(f"Error processing chunk: {e}")
            continue

    # Join the summaries of all chunks
    return "\n".join(summaries)


def perform_semantic_search(query, top_n=3, title_overlap_weight=1.8):
    # Preprocess query
    preprocessed_query = preprocess_text(query)

    # Tokenize and encode the preprocessed query
    query_tokens = tokenizer.encode(preprocessed_query, add_special_tokens=True, max_length=MAX_TOKEN_LENGTH,
                                    truncation=True, padding='max_length', return_tensors='pt')

    # Compute BERT embeddings for the query
    with torch.no_grad():
        query_outputs = model(query_tokens)
        query_embedding = query_outputs.last_hidden_state[:, 0, :].numpy()

    # Compute word frequencies in the preprocessed query
    query_word_freq = {word: preprocessed_query.split().count(word) for word in preprocessed_query.split()}

    # Retrieve precomputed document embeddings from the database
    records = File.retrieve_files_from_db()

    if not records:
        print("No records found in the database.")
        return []

    # Calculate cosine similarity between query and precomputed document embeddings
    similarity_scores = []
    for file_info in records:
        document_title = file_info['name']  # Title is at index 1
        document_text = file_info['content']  # Content is at index 3
        document_embedding_blob = file_info['embedding']  # Embedding is at index 4

        # Combine title and content for comparison
        combined_text = document_title + ' ' + document_text

        # Preprocess combined text
        preprocessed_text = preprocess_text(combined_text)

        # Calculate the relevance score based on the most repeated words in the query
        relevance_score = sum(query_word_freq.get(word, 0) for word in preprocessed_text.split()) / len(
            preprocessed_text.split())

        # Convert embeddings from bytes to numpy array
        document_embedding = np.frombuffer(document_embedding_blob, dtype=np.float32).reshape(-1, 768)


        # Compute cosine similarity between query and document
        cosine_sim = cosine_similarity(query_embedding, document_embedding.reshape(1, -1)).flatten()[0]

        # Calculate word overlap between query and document title
        query_title_tokens = tokenizer.encode(preprocessed_query, add_special_tokens=True, max_length=MAX_TOKEN_LENGTH,
                                              truncation=True, padding='max_length', return_tensors='pt')
        document_title_tokens = tokenizer.encode(preprocess_text(document_title), add_special_tokens=True,
                                                 max_length=MAX_TOKEN_LENGTH,
                                                 truncation=True, padding='max_length', return_tensors='pt')

        title_overlap_score = cosine_similarity(query_title_tokens, document_title_tokens).flatten()[0]
        title_overlap_score = title_overlap_weight * title_overlap_score
        # Adjust similarity score based on relevance score and title overlap score
        similarity_score = cosine_sim * relevance_score * title_overlap_score

        # Append normalized similarity score
        similarity_scores.append(similarity_score)

    # Normalize similarity scores using Min-Max scaling
    min_score = min(similarity_scores)
    max_score = max(similarity_scores)
    normalized_scores = [(score - min_score) / (max_score - min_score) for score in similarity_scores]

    records_list = list(records)

    # Get indices of top documents based on normalized similarity scores
    top_indices = np.argsort(normalized_scores)[::-1][:top_n]

    top_indices = top_indices.astype(int)

    # Retrieve top documents
    top_documents = [(records_list[i]['path'], records_list[i]['name'], records_list[i]['summary'], records_list[i]['user__username'], records_list[i]['upload_date'], normalized_scores[i]) for i in top_indices]

    return top_documents

#print(records_list[0])
# {'id': 2, 'user__username': 'hilali13', 'name': 'How to Flagg PIR.docx', 'path': 'How to Flagg PIR_tMavBCb.docx', 'content': 'Introduction : This document serves as a guide for flagging Purchase Information Records (PIR) using the transaction code MEMASSIN. Flagging PIR involves the process of marking specific purchase information records for further action or attention. The MEMASSIN transaction code is utilized to execute this flagging procedure effectively. By following the instructions outlined in this document, users can learn how to efficiently flag PIR and streamline their procurement processes. T.code: MEMASSIN Then, SAVE image4.png image1.png image2.png image3.png Mass Maintenance: Purchasing Info Rec. E, Restrictions [% Old Values | (B/B =p) |=I=) [2] || Purchasing ... Pur... I. Plant P) New Values | <> & Purchasing ... Pur... I. Plant P [lls300809469 Maco 0 Mago v 1 Entries Mass Maintenance: Purchasing Info Rec. @ BB Import Data from File HS Import Data from Buffer opfect t96#*e BUS3003 Purchasing Info Rec. Variant Name | Tebles_ GE Short Description Table Name 1-SELECT ENE TABLE Mass Maintenance: Purchasing Info Rec. em tend variant v Data Records to Be Changed Restrict Data Records to Be Changed 1 Select the PIR Purch. Organization MASO To ing play Info record category To ee Plant ASO To ag plant Mass Maintenance: Purchasing Info Rec. E, Restrictions [% Old Values |B [Be ing ... Pur... I. Plant New Values 1 Entries Select fields <> Selection criteria Purchasing ... Pur... I. Plant a [lls300809469 aso 0 Mago ~ Purchasing Group Quotation | Quotation Valid from Rejection Indicator 4) ] Rounding Profile Settlement Group 1 Settlement Group 2 Settlement Group 3 Shipping Instr. “ Staging Time a ¥ Standard PO Quantity ¥ <> <> <> He =|F Current number oO Maximum number 16', 'embedding': b'\xc9\x15\'\xbf0\x12\x95>\x8e\x8bw\xbe\xd2\x83\x94>7\x8b\xba\xbe\xc1_\xcd>(\xb9\xba>zf\xba\xbe\xc4as\xbe3\xd8\x8b>\x84\x84\xe1<h\x92\xf1\xbe\xe8\x86\xfc\xbe\xd9v$?u^\xdc>\xdbJ\x9e>g\xe19>\xadq\xef>\xb0U\xac\xbdb\xd1\xb0>f\xc9\r>\x95n\x12\xbf\xde\x9c\r?\x01K\t\xbe\x16\xa7\x15\xbe\x8a\x8fm=\x96\xeb\xe9\xbe\x1d\xbe\x84\xbf\xe6\xbb\xca\xbe\xce\xa3D\xbe\x8d\xea\xa0\xbe\x9a\xde\x1e?\xd6\xf6\xce=k\x98\x17\xbf)\xf3\xac>\xc8\r\xc2\xbe\x0157>tUe=\x1d\x99{?\x0e*\r\xbe\xb3j\xb1=$\x89!>\x9c*\xef>r\xdf\xb1\xbd\xb2\xca\xca\xbe\x9a\x08\xf9\xbe\x81\xee\x88\xc0Q\x88\x8b=\x80rp\xba\xbegS\xbf\x9d\xad\x08>0\x16\xd4\xbeo\x81\xff>\x12P\t?z{\x9b\xbe5\xe4\x1a?\x85\xca#>\xb2z5\xbf\x95h\xdf?\xe7E\x04\xbf\xecD\xec>\xbcN\x94>\xff\x8c\xf9\xbe\x87\x0f\x10?~\xac\\\xbex\xdcj?\xf2<\xd8=\xb9\x00V\xbe$A\n\xbfO\xb3\x99>f\xdd\x06\xbdW!\xd3>\x186\x0c?\xe6\x96\xd7>6!S>\xba\xca\xfb=\xb4 a=\x96$P?\x99\x97\xe5\xbe\x06~\xb2\xbd\xd7Q\xaf>\x8f.\xb5=V\xae\x19>?\xbb;\xbf\r\r\xa2> \x14\xff=\x87\x80\x97>\x95<@\xbf\xf3,8\xbf!1\n?]\xef\xe0>\x8c\xddT><\x0c\x1e?\x85N\xbc\xbd\xc0K\x9c\xbd\xcc\xc3\xce>\xa4x\xac>\x82\x9a\xe0>2C\xa6>\x15\xf9\xd5\xbc\xac?^\xbd\xaa1*?P\xb7\x82\xbe\xdb]!\xbf\xf6\x87\xae\xbe\nqk>\xe1\x96|\xbf-\xa2l>\x98`2\xbf\x94>\x0e=E\xce\xdc\xbc\x18\xda-?b$\x14\xbfw\xee5\xbf\xdc\xdd+?\x00\xa7v:\x94s\x13?N\xb6\x13\xbf\xc2\x0e\xf8>y\xd9\xb7\xbe-\xf5\xf2=\xc4|\x8b>\x01\xb3Z<\xb2\xc9=>\xb8.K\xbe<\xe5\x11?\xe0\xdb\x91=\x0e@\x9b\xbf\xeb\r\xc1>bm\x99?\xd4\xfb\xfa\xbd\xeb\xe0\x1c\xbe\x81e%\xbe\xec\xd2\t>r\x1d\xb8\xbe5\xd5\xea\xbe1\x14\xcd\xbd\xb8\xe8\xaf>\xf7u\x05\xbe.l\xff=m9v\xbf\x14\xd1e\xbfD\xd5z\xbfIw(\xbfT4\x1e=+\xcb\xd8\xbe\xa9\x08\xd8>2B\xb8>S\x03\x16\xbf\x915)\xbe\x9a\x81\x1d?\x12\xce\xca\xbe\xdf\xbf_\xbe\xf3\xff\x1a\xbf\xfcd\x92\xbeP\xaf\xb4;\x1a\xac(\xbeC\x00\x06\xbd\xe63S>\xc6\x9a>?V~\xac\xbd\xfdqK?K\x00\xd2\xbe\xf8\xe3\r?\x12\xbd)\xbe>\xf7\x92><0\xee=\x83z\x12?\xb8H\x93=*\xf2"\xbf\xd4\x11\xc6\xbb\x95`\xab\xbd\xff>\x83?\xf1\xed\xc5\xbe\xd8\xcbr\xbef|V>\x11\x97#>R\xb9\xee>\x8a\x9eB?\xab\xe4\xcf\xbe\xa6\x15\xeb\xbea_\x9a\xbe\xa9S\n\xbez\x93^>\xd8\xca\'\xbf\xc6\xac2?\xca\xaf\x8c>\x9e\xe5\x0e?U\x9e\x8d\xbe\x17%\x86>\xc6\xed\x97\xbf\x80\xb0\xdc\xbe\xbe\x1b\x03?\xe9ZG>\x91T\x8e?\xbf\x87%?\xf6\x10\x11\xbe\x1f\x97\x04>\xe7\x98\x86\xbd\xdbl\x07\xbf*\x08l>\x86\x03\xb0>\xc6\xdb\xab\xbe\x17\xe2\xa9>E\x8e\x02\xbf\xc6s\x0b@V\xce\xb4>\x1c\x12~\xbe\xbc\xcbC\xbdZr,\xbd\xff\xe9\x0f\xbfJ\x80,\xbf\xac\x84/\xbfQ\xc9Z>\x94\'\xd0\xbd\xcb\xbfn\xbe\x9aa\x1e\xbe\xea\x17\xc6\xbc\xd0WO<\x9e\xac!\xbe\x84\x14\xf1\xbej\xb5\x1b\xbe2\x1b\xa3\xbe\xf5\xa7\xb1>l\x03\x1d=B\xdd)\xbe\xf2\xe3E\xbd\x18\x8d\x18\xbe\x18\xa4\xe0>\xc1\xc3\xe1\xbf\xe3*\x0b?3/r\xbf*\xaf&\xbfg8\'\xbcn\xad\xc8\xbc\xc0\xc7\x0b<UxC>\xafy2\xbet\xf7\x90\xbdp|n\xbd\xda1\x00>@\x80A?~\x18]\xbe\x95\xf9"\xbf\x8a\xfa\x9a=\xad\xe4\x0f\xbe\x16x\xae\xbd\xca\x0b\xf8\xbe(\xb0\xfb<\x91\x83\xc1>\x0e\xeeO>u#\xd1>\xcb\xda\x8c=\xb2\xae\xc5\xbdr\xe0\x9f>\xa4\x16\xe0<\x020\x81\xbe\x8f\xe3\xac>\xfe\x89\'\xbf\xc24\x83\xbf\x95\xad0\xbf\x12\xd1!>\xb8\xa3\x0c>\x1c\x9f\xbf>qcS\xbe\xb6p\xbe\xbe\xdaI\xe9>.\x9b\x02\xbfi\xa7\xe2\xbeN\x04h\xbd\xd6\xac\x83>\xda\xa0\xa1\xbe\x1e\xc4\xd3\xbe\x8e\x83#?\xbe\'V\xbc"\x91\xae\xbe\\o6?\x00p\x88\xbep\xa1\xe6\xbe\xe9{\xa4\xbe\x01\xb4\x03\xbf\xce=\xb3=\x02\x8c\x02\xbf\xdd\xb0\x91>xL{<\x05\x8f`\xbf\xcb\xf3\x12?\xf8T\x19\xbf+\xe3\xd2>\x96\xa9\x01>\xf3}~\xbf\xb4\x11\xae>V\x94\x0b=F?$\xbe\x1c\xed\x96\xbe\xe8\'\x8b\xbfjZ\xee=\xbe[\xdf\xbe\xf8\xd3\xbe>%\xbe\xdf>\xc7\xc8X\xbf\x88\x1bX?\xf2B.\xbe\x19.,?(\xae\x95\xbe>\x05V=&\xad\xce\xbe\x1c\x9es;\xfe|\x8f\xc0\xda\xdc|?\x16\x89\xc4\xbe\x83\xe9\x1a\xbe\xd5\xf6_>\xfe\xcb\xcb>\xa5\xe67?W\x0b\xbd>\xac\xb8\x17\xbf=\xcd\x17>\x11&\x03?\xb5\x98G?\xb75\xe6\xbeU\x83\xae>8\xc1\xef\xbb\xee\xf2\x9d\xbd\xd0\xfcQ?\xfe\xf4\xd5=\xfb\xde\xb8>p\x9c\xb0\xbe0\xd9\xf3\xbe\x15.n\xbfm\xa7M?D\xbd\x82\xbe\x9aF{>\x98,\xd9=\xf4Q!\xbfD\x1f\xab>GF\xa2\xbeR\xe8\xba>\x98h\xf9\xbe\xce\x0f\xd0\xbe3\x1cX\xbe\'\x1aZ>\'G\x80\xbe\x90\x17\xf6\xbew\t\t\xbf,\xc9\x1b\xbf\xe4\xb7\xe5>B\xd1\x12\xbf\x8ds\xea>\x9a\x03\x88\xbe\x90\xbc\x13==GE\xbe\xfc\x95\x0e?\xe6\xa9\x9f\xbc\xf0\x03\xa1\xbb\xb00\x97?\xf0\x1a\x98=,\xb8\x12?\xbf\xac=\xbeb\xd5.>|/\x11>\x0f>\r?\xad\x80\x9c\xbe9\x8b\x85\xbd\xa6\x90~>\xd6A\x81\xbe\x9b\xb0\xd6\xbe\xbaE\xd0>\x0c\x19I?~p.\xbe<\xf1\xec\xbe \xa6I=\xae\xfd\x13\xbeW\x1cC\xbf\xaa\xf1?>\xe5\xbc\xdc\xbe}\xf8\x19\xbf&\xbf>?\xa99A\xbf\xe7w.?\x06\xc9\x8b\xbe\x9f\xd0\xc7\xbf\xa4\x1f\x8d\xbe\xb3N\xfb\xbe\xb0DL=\x00U^\xba\xa7\xda\xf5\xbd\\\x83C>,\xce?\xbf\x1f\xdf\x83\xbc\x94\xcf\x00?{7!?\x90\xc2\x92\xbep\xb6a?Y\xab\xdc\xbe\x88\x17\xeb>T\xf3\r\xbe\xde@\xe8>\x82[0\xbe\xde\r\xf5\xbd\xd9\x99Z?\xa1\r\xde=\xe6)\xd9\xbd\x91\xdb\x81>\x89\x8d\x0f?\x06%\xa1\xbe\x93\xf9Y?\x14FR\xbd\x8eI\x10?t#\xb1\xbd\xf3\xff\xfe\xbe\xce\xc3\xa7>\xb8\xd8\x12?*\xa5\xf0\xbe\x85<n\xbfR\x14\x16\xbf\x9f\xf8R>\x9f\x9a\xd8\xbd[x\xf7\xbc+Q\x0b?\xf2\xcc|>\xb8\xb9\xea<\x7f\xb6\xd0>\x07\x18/\xbf\x11t\x97\xbe\x9d\x95+?\xd1&\x18?\xec\xeb\xab>\xc7k\xa7\xbd\xde\x87\n\xbf\xf0\xcb%\xbf\xe9\xd5\xdb\xbe\xe0\xa9\xd0\xbeh\x8e\xa1\xbbY]\xd3=t#\xb5>\x82\x91\x8b\xbe\xac\x7f\n>W\xca%\xbem -\xbd=\xa3\xb7\xbf\xfa\xca\xee\xbe\x84t\xe0>\xbe\xc0\x9d>\xee\x8d\x1d\xbe\xc0\x00+\xbe\xb2\x10\x16?\x1c?\x84<\xb4P$?\xdd\xdd\x7f\xbe_\xbd&\xbf@|\x19\xbe\xccj\x06;\x90\xa9\x11?\x9f\x1c\xfd>V\xc9\x00\xbf\xe6T\x0e\xbe;O9?\xa6\xeb\x9f\xbd\xcc\xea\xb6\xbd\xe2h5=\'\x03\xb7\xbe6\xd6\xff=\x13\nn\xbd\x8e\xb8s\xbe\x94\xe8\x91=\x19\xa1$\xbf\x01;\x1a\xbf\xa7t\xc4>%\x87\x8c>\xf4\'\xe1\xbf3\x08\x1d\xbf$OX?\x01k\xb6>\xeb\xa5\x83>\x88{\x8a\xbe\xce\xfa\xa6\xbe\xc0\x12\xd9=\x1a\x93\xb9<T b\xbe\x9a\xbc\xb6\xbe\x08.\xcf\xbc\xfb\xd2\x9f=f\xf1\x84>\x8f\xdc\xff>\x07\xf4\xa0>U\xadX=\xd81>\xbc\xee\xff\x83\xbe\xb6\xc2S\xbe6\x8d\x8d\xbe\xff\n\x94>28\x94>\xe8\xed\xca>3\x9c#\xbe\x14g\xee\xbe\xea\x1bR\xbfJ\x80\x92>\x15\x9d\x02>\xf6\x8a\xe8\xbd\x01\xeb\x86\xbe\x9c\x97O\xbf/\x18\xc5>6\xdd8\xbe\x1eBT?\xe6\xf0\x95?LCz\xbb\xb2\x8b\x89>\'Y#>|\xb8\x12>\xee\x89\x11\xbf>X\xcf>\x19\x137?")\x0e?\x80\xa7\x9c\xbe\xf0\xa1m=\\\xf2\xcb=\xae\xed\x8c\xbd\xa2\x89\xc3>b\x91j=\xc8\xba\x0e?+Y\xb2=\xb9\x89/\xbe\xe7o;>@?\x07>\xb9\t\x9c\xbe\xdf+-\xbe\xb8\x0e\xd2>\xba :\xbeA\xefz>:\xac\xf2>v^a\xbf\x0b\x17\xe9\xbd \xb1\xaf>\x14\x95\xb2\xbe\xcd\xe7w\xbf\x83\xa8\xe0><!\xf1\xbc\x9f\xb5\xfb\xbe\xff\x03\xe1>\xb4\xef\xcd=\xe0\x89\xa9=\x80\xe4\x9f\xbf\x80\x8b"\xb8\x13\xa17\xbe_50\xbe\\h\x9a>\x1b3P?\xe8\x8dH>\x19\x11\xd5\xbe\x9el~?p\x182\xbf\xfe\xf7\x80>>\xaf\x06?^\xfb\xaf\xbe!\x02\x96\xbbv\xf8\xab>\xc4\xbd\xb6<\x03\x18\xb2=\xcbg\t?\xd7\xce\x93\xber!P\xbf\xc4h\x81>\x90\xb7%=!Hy>v\xf7A\xbe\xc2\x89\xd6=\x1b\xe4\xbe\xbe"\xec\xb1\xbe\x99\x0f"?\xac?\x05>g\xd0\x9c>\x043(>\xa9*\xb7>\xdc\x9a\x91>H\xe2}?\x8c\xdc:>\xec\x9b\xca\xbe@\xaa6\xbf\xc2\xc5\xe5>\xa8 \xb7>\x028\xc9\xbd\x04\x02\x9a<\xc2?\x11>\x02Cj?\xea\x07\xa1\xbe\x8dR\xbd>p`d\xbf\x10\xb0\x93>\xaa\xc1\x88=\x16\xe6\t\xbeROi>\xe7P\x04?\x8a\xd7\xe8>\xaaM\x13\xbf\x1a%\xbb\xbel\xd5\xd2=\xff\x8c)?%\x18\x13\xbfxc\xcb>\xeeLD\xbec\x88\x0f>\xf0\x8f\xae\xbb0\xbdE?\xe2\xd5\t>\xd4\xd5\x8c\xbe.J\x87\xbf\x81\xee\xfd>i~\xa9\xbeh\xcd\x1b<\x0cso?4\\\xe6\xbe\xaa\xcc3\xbf1f??E\x19\xc9\xbe\xcbz\xd7\xbe\xc1\xdc\xa6\xbeeU`\xbe\xf8\xec\xd8\xbd\xe6\x17\xe6=agO>\xc5&\xee=\x18\xaa0\xbf\x8c\x17\xcc\xbe\xc0\x9c\xbe\xbe\x1b\x1b\xa3\xbe\xe5\xa4>\xbe\xc1\'\xf1>\xed\x08(\xbc\xfc\xd4\x16?\xb9\x8c\x14?\xb8\xf2\xfd\xbe\x0f_^=,t1>\xd6\n\x97> \r\x06\xbf\xfd:\xeb\xbd+\x11:?\xa2\xc8\\>\x05\xe8M\xbf\xd8Nq\xbe{\xf7\x93\xbe\t0\xf7=\xfd\xbfG=\x06(:\xbf\xe7\xb4\xa0\xbf\xa3\x9a\xd3\xbe\xc6\x0f\x0f>R\x06B\xbf\'\xb3\xb8>\x13\xd7\xf1>\xd3\xef\xf6\xbeA=\x80\xbf!\xae\x81>b\n\x03?p=\x10\xbdk\x1fV>|p\xa4<|<\xa4\xbc#\xf4\xe2>\xac\xbf\x1c?onw?\x84{B\xbe\x81o\xf2>l\xf0U\xbe\x05zS\xbf/\t\xbe\xbe\x98\xaa\x18\xbe\xa8"\x11=\xd8p\t\xbe\xa7\x828>\x07\x01\xee\xbc\xfd\x80A\xbe\xe2\xe26\xbe\xb1\xe0\xb4>4\xae\x95>\x87@(?\x86a\x9f\xbe|\xddp?Yu.\xbe\xf0\x84&\xbe\'9\xbb\xbe\xf6\xe5\x83>o\x17\t>\xd4\x1c\xd3=\xc6*\xaf\xbe\xdf#\x7f\xbd.\xbd\xa6>\xad\x9d\x02\xbf\xf6\xd8\n\xbf\xf07\x12\xbc\x95)V\xbf\x1d\x08\xe2>p\xbe\xa5?\xd3\xdeu\xbeg\xae\xec>\xd2\xdaQ?\xcc\xde3\xbe\xc2\x81\x16?\x9f\x9b\x8b> Gw\xbe\xaf\xab\xb5>\x8f\xce\x8d\xbe\xd4\xbeN?(2\xb4\xbeW\xcf\xda\xbd\xaf\xc7\x8b>\x1d\xac\x12=\xb6\xe5X?I\xaf\x1a>\x07)\x98>\xb0T\xae=8\xcf\x00=\xe8\xe7\x9b>\xa8\x04i=\x82\x1f\x84?\xb2v\x82\xbe@\xce!\xbf\xf7Q^\xbe\xef\xe2\xe0=P\xf5\t?\x9e&l\xbe\x12\xb38\xbc\xe5$\x10\xbf\x12\x92\x88\xbd\xa1\x01\xd0=\x1b\xb4\x9b=K\xf5q\xbf\x12\x97\xa6\xbe\n`\x1e\xbf\xcb@T>\x0c\r\xff>\xa7\x8d\x83>p\x87\xfb\xbc\x9c\xf2\xe8>S\x88\x0c\xbe5\xec!\xbf\x14\x1dE>of\x02\xbf\xee\xd3\xa4>v.u\xbd\x9b\x00\xb5<(v\xeb\xbe#\xba\xef>\x11BE?\x99\xad8?l\xdb\x00?\xbe\x1c\x1b\xbf\xf8tL>$7\xfd>\xdb\xd3e?\x0f\x93|>Nn>\xbe\x8b\x00D\xbf\xfe\x19\xbe\xbd\x1aY\x1f\xbf-\xf7\x92\xbeP\xfd\xf1<\x97\x908>\xef[\xf0\xbd\xf8\x88y<?m\xce\xbe\xe2\x99\x93>2\x1dM\xbebH\x90\xbe0\xdai\xbe\x86\xdc\x12?\x10A\xcd\xbe', 'summary': 'Flagging PIR involves the process of marking specific purchase information records for further action or attention. The MEMASSIN transaction code is utilized to execute this flagging procedure effectively. By following the instructions outlined in this document, users can learn how to efficiently flag PIR.', 'upload_date': datetime.datetime(2024, 4, 1, 16, 48, 43, 578329, tzinfo=datetime.timezone.utc)}

