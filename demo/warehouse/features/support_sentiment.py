# feature: support_sentiment
# Computed in Python from the support_tickets column with a sentiment model.
# There is no SQL here for Tether to parse. This is the edge it must REFUSE to infer,
# rather than guess at, and the refusal is published as the honest failure case.
import pandas as pd
from sentiment_model import score  # noqa

def build(customers: pd.DataFrame) -> pd.Series:
    return customers["support_tickets"].apply(lambda t: score(t))
