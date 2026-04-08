"""
src/sentiment/analyser.py
Sentiment analysis on product reviews using VADER (primary) + TextBlob (secondary).
Downloads required NLTK data on first run automatically.
"""
import sys
import logging
import nltk
import pandas as pd
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from textblob import TextBlob

from src.exception import CustomException

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Download required NLTK data silently on first use
for _pkg in ("vader_lexicon", "punkt", "stopwords"):
    try:
        nltk.data.find(f"tokenizers/{_pkg}" if _pkg == "punkt" else f"sentiment/{_pkg}" if _pkg == "vader_lexicon" else f"corpora/{_pkg}")
    except LookupError:
        nltk.download(_pkg, quiet=True)


class SentimentAnalyser:
    """
    Enriches a reviews DataFrame with sentiment scores and labels.

    Adds columns:
        vader_compound  – float  [-1, 1]
        vader_label     – str    Positive / Neutral / Negative
        tb_polarity     – float  [-1, 1]   (TextBlob)
        tb_subjectivity – float  [0, 1]    (TextBlob)
        sentiment_label – str    final blended label
        sentiment_score – float  blended score in [0, 1] for easy plotting
    """

    POSITIVE_THRESHOLD = 0.05
    NEGATIVE_THRESHOLD = -0.05

    def __init__(self):
        self._vader = SentimentIntensityAnalyzer()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyse(self, df: pd.DataFrame, text_col: str = "Comment") -> pd.DataFrame:
        """Return df with sentiment columns appended."""
        try:
            if text_col not in df.columns:
                raise ValueError(f"Column '{text_col}' not found in DataFrame.")

            df = df.copy()
            texts = df[text_col].fillna("").astype(str)

            vader_results = texts.apply(self._vader_score)
            df["vader_compound"] = vader_results.apply(lambda x: x["compound"])
            df["vader_label"] = df["vader_compound"].apply(self._vader_label)

            tb_results = texts.apply(self._textblob_score)
            df["tb_polarity"] = tb_results.apply(lambda x: x["polarity"])
            df["tb_subjectivity"] = tb_results.apply(lambda x: x["subjectivity"])

            df["sentiment_label"] = df.apply(self._blend_label, axis=1)
            df["sentiment_score"] = df["vader_compound"].apply(
                lambda c: round((c + 1) / 2, 4)   # map [-1,1] → [0,1]
            )

            logger.info(f"Sentiment analysis complete on {len(df)} rows.")
            return df

        except Exception as e:
            raise CustomException(e, sys)

    def summarise(self, df: pd.DataFrame) -> dict:
        """Return aggregate sentiment stats per product and overall."""
        try:
            if "sentiment_label" not in df.columns:
                df = self.analyse(df)

            summary = {}
            for product, grp in df.groupby("Product Name"):
                counts = grp["sentiment_label"].value_counts().to_dict()
                total = len(grp)
                summary[product] = {
                    "total_reviews": total,
                    "positive": counts.get("Positive", 0),
                    "neutral": counts.get("Neutral", 0),
                    "negative": counts.get("Negative", 0),
                    "positive_pct": round(counts.get("Positive", 0) / total * 100, 1),
                    "avg_sentiment_score": round(grp["sentiment_score"].mean(), 3),
                    "avg_subjectivity": round(grp["tb_subjectivity"].mean(), 3),
                }
            return summary

        except Exception as e:
            raise CustomException(e, sys)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _vader_score(self, text: str) -> dict:
        return self._vader.polarity_scores(text)

    @staticmethod
    def _textblob_score(text: str) -> dict:
        blob = TextBlob(text)
        return {"polarity": blob.sentiment.polarity,
                "subjectivity": blob.sentiment.subjectivity}

    def _vader_label(self, compound: float) -> str:
        if compound >= self.POSITIVE_THRESHOLD:
            return "Positive"
        if compound <= self.NEGATIVE_THRESHOLD:
            return "Negative"
        return "Neutral"

    def _blend_label(self, row) -> str:
        """
        Use VADER as primary signal; fall back to TextBlob polarity
        when VADER is borderline neutral.
        """
        if abs(row["vader_compound"]) > 0.1:
            return row["vader_label"]
        if row["tb_polarity"] > 0.05:
            return "Positive"
        if row["tb_polarity"] < -0.05:
            return "Negative"
        return "Neutral"