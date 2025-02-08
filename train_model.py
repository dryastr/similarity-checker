import re
from Sastrawi.Stemmer.StemmerFactory import StemmerFactory
from Sastrawi.StopWordRemover.StopWordRemoverFactory import StopWordRemoverFactory
from gensim.models.doc2vec import Doc2Vec, TaggedDocument
import psycopg2
import os

INDONESIAN_STOPWORDS = set(StopWordRemoverFactory().get_stop_words())


def preprocess_text(text):
    factory = StemmerFactory()
    stemmer = factory.create_stemmer()
    text = text.lower()
    text = re.sub(r'[^a-z\s]', '', text)
    tokens = text.split()
    tokens = [word for word in tokens if word not in INDONESIAN_STOPWORDS]
    stemmed_tokens = [stemmer.stem(word) for word in tokens]
    return stemmed_tokens


def get_documents_from_db():
    conn = psycopg2.connect(
        "dbname=db_similarity user=postgres password=guitarflash215 host=localhost"
    )
    cur = conn.cursor()
    cur.execute("SELECT id, title, file_text, vector FROM documents")
    documents = cur.fetchall()
    cur.close()
    conn.close()
    return [{'id': doc[0], 'title': doc[1], 'file_text': doc[2], 'vector': doc[3]} for doc in documents]


def prepare_and_train_model():
    documents = get_documents_from_db()
    tagged_data = [TaggedDocument(words=preprocess_text(doc['file_text']), tags=[
                                  str(doc['id'])]) for doc in documents]

    model = Doc2Vec(vector_size=20, window=2,
                    min_count=1, workers=4, epochs=20)
    model.build_vocab(tagged_data)
    model.train(tagged_data, total_examples=model.corpus_count,
                epochs=model.epochs)

    model.save("d2v.model")
    return model


if __name__ == "__main__":
    model = prepare_and_train_model()
    print("Model berhasil dilatih dan disimpan sebagai d2v.model")
