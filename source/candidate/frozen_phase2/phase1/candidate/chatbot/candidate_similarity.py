"""Use the same cosine-distance score convention as native semantic search."""
import math


def cosine_similarity_score(query, vector):
    if len(query)!=len(vector) or not len(query):
        raise ValueError('Embedding dimension mismatch')
    denominator=math.sqrt(sum(float(v)*float(v) for v in query)*sum(float(v)*float(v) for v in vector))
    if not denominator:return 0.0
    cosine=sum(float(a)*float(b) for a,b in zip(query,vector))/denominator
    return max(0.0,min(1.0,(1.0+cosine)/2.0))
