# Simple AI content detector
# For text — check patterns
# For images — use a pre-trained model

from transformers import pipeline

# Load AI text detector
detector = pipeline("text-classification", model="roberta-base-openai-detector")

def detect_content_origin(text):
    result = detector(text)[0]
    label = result["label"]
    score = result["score"]
    
    if label == "LABEL_1":
        return f"AI Generated (confidence: {score:.2%})"
    else:
        return f"Human Written (confidence: {score:.2%})"

# Test it!
sample = "The quick brown fox jumps over the lazy dog"
print(detect_content_origin(sample))