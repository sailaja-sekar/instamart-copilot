import os

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

import mock_llm

POLICY_DIR = os.path.join("data", "policies")

# ---------- Task 1: chunk the documents ----------
def load_documents():
    docs = {}
    for name in sorted(os.listdir(POLICY_DIR)):
        if name.endswith(".txt"):
            with open(os.path.join(POLICY_DIR, name), encoding="utf-8") as f:
                docs[name] = f.read()
    return docs

def chunk_words(words, size=40, overlap=10):
    step = size - overlap
    chunks, start = [], 0
    while True:
        chunks.append(" ".join(words[start:start + size]))
        if start + size >= len(words):      # this chunk reaches or passes the last word
            break
        start += step
    return chunks

# ---------- Task 2: vectorise and retrieve ----------
class PolicyIndex:
    def __init__(self, size=40, overlap=10):
        self.chunks = []
        for source, text in load_documents().items():
            for piece in chunk_words(text.split(), size, overlap):
                self.chunks.append({"source": source, "text": piece})
        self.vectorizer = TfidfVectorizer()
        self.matrix = self.vectorizer.fit_transform([c["text"] for c in self.chunks])

    def retrieve(self, query, k=3):
        scores = cosine_similarity(self.vectorizer.transform([query]), self.matrix)[0]
        best = scores.argsort()[::-1][:k]
        return [{"source": self.chunks[i]["source"],
                 "score": round(float(scores[i]), 4),
                 "text": self.chunks[i]["text"]} for i in best]

INDEX = PolicyIndex()

def retrieve(query, k=3):
    return INDEX.retrieve(query, k)

# ---------- Task 3: augment and answer ----------
POLICY_SYSTEM = (
    "You are a POLICY ASSISTANT for Instamart support. Answer the question using only the "
    "information in the CONTEXT. If the context does not contain the answer, say that you "
    "could not find the information in the policy documents."
)

def answer(question, index=None):
    index = index or INDEX
    hits = index.retrieve(question, 3)
    context = "\n".join(f"[{h['source']}]\n{h['text']}" for h in hits)
    messages = [
        {"role": "system", "content": POLICY_SYSTEM},
        {"role": "user", "content": f"CONTEXT:\n{context}\nQUESTION:\n{question}"},
    ]
    response = mock_llm.chat(messages)
    return response.choices[0].message.content, [h["source"] for h in hits]

# ---------- Task 4: evaluate retrieval and grounding ----------
def evaluate(index, label):
    rows = pd.read_csv("data/raw/policy_eval.csv", keep_default_na=False)
    doc_ok = fact_ok = fallback_ok = n_answerable = n_unanswerable = 0
    failures = []
    for _, r in rows.iterrows():
        text, sources = answer(r["question"], index)
        if r["expected_doc"] == "NONE":
            n_unanswerable += 1
            if text.startswith("I could not find"):
                fallback_ok += 1
            else:
                failures.append((r["question"], "should have said it could not find the answer"))
        else:
            n_answerable += 1
            d, f = r["expected_doc"] in sources, r["expected_fact"] in text
            doc_ok += d
            fact_ok += f
            if not (d and f):
                failures.append((r["question"], f"doc found: {d}, fact in answer: {f}"))
    print(f"\n{label}: {len(index.chunks)} chunks")
    print(f"answerable: expected doc in top 3: {doc_ok}/{n_answerable} | "
          f"expected fact in answer: {fact_ok}/{n_answerable}")
    print(f"unanswerable: fallback answer: {fallback_ok}/{n_unanswerable}")
    for q, why in failures:
        print("  breaks:", q, "->", why)
    return doc_ok, fact_ok, fallback_ok, failures

if __name__ == "__main__":
    per_doc = pd.Series([c["source"] for c in INDEX.chunks]).value_counts().sort_index()
    print("chunks per document:", per_doc.to_dict(), "| total:", len(INDEX.chunks))
    assert len(INDEX.chunks) == 15
    assert per_doc.to_dict() == {"delivery_policy.txt": 3, "escalation_policy.txt": 3,
                                 "payment_policy.txt": 3, "privacy_policy.txt": 2,
                                 "refund_policy.txt": 4}

    top = retrieve("refund policy late delivery")
    print("\nquery: refund policy late delivery")
    for h in top:
        print(" ", h["source"], h["score"])
    assert all(h["source"] == "refund_policy.txt" for h in top)

    sample_text, sample_sources = answer("Who must approve a refund above INR 1000?")
    print("\nsample answer:", sample_text, "| sources:", sample_sources)

    d, f, u, _ = evaluate(INDEX, "OVERLAP 10")
    assert (d, f, u) == (12, 12, 2)
    d0, f0, u0, failures0 = evaluate(PolicyIndex(size=40, overlap=0), "OVERLAP 0")
    assert len(failures0) >= 1
    print("\nRAG CHECKS PASSED")