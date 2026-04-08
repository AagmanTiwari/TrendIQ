"""
src/forecasting/price_forecaster.py
Time-series price forecasting using Facebook Prophet, with automatic
fallback to linear regression if Prophet/Stan is broken.
"""
import sys
import logging
import warnings
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from src.exception import CustomException

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)


class PriceForecaster:
    """
    Forecasts product price trends.

    Tries Prophet first. If Prophet/Stan is not working (common on M1 Macs
    and fresh envs), automatically falls back to numpy linear regression so
    the rest of the dashboard never breaks.
    """

    def __init__(self, forecast_days: int = 30):
        self.forecast_days = forecast_days

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def forecast(self, price_df: pd.DataFrame, product_name: str = "") -> pd.DataFrame:
        """
        Forecast prices for the next forecast_days.
        Returns DataFrame with columns: ds, yhat, yhat_lower, yhat_upper, trend
        """
        df = self._prepare(price_df)
        if len(df) < 2:
            logger.warning(f"Not enough price history for '{product_name}'.")
            return pd.DataFrame()

        # Try Prophet -> fallback to linear regression
        try:
            result = self._forecast_prophet(df)
            logger.info(f"Prophet forecast done for '{product_name}'.")
            return result
        except Exception as prophet_err:
            logger.warning(
                f"Prophet failed for '{product_name}': {prophet_err}. "
                "Using linear regression fallback."
            )
            try:
                result = self._forecast_linear(df)
                logger.info(f"Linear regression forecast done for '{product_name}'.")
                return result
            except Exception as e:
                raise CustomException(e, sys)

    def check_drop_alert(
        self,
        forecast: pd.DataFrame,
        current_price: float,
        drop_threshold_pct: float = 10.0,
    ) -> dict:
        """Return an alert dict if a predicted price drop >= threshold."""
        if forecast.empty or current_price <= 0:
            return {"alert": False}

        future_only = forecast[forecast["ds"] > datetime.today()]
        if future_only.empty:
            return {"alert": False}

        min_row = future_only.loc[future_only["yhat"].idxmin()]
        predicted_min = min_row["yhat"]
        drop_pct = (current_price - predicted_min) / current_price * 100

        if drop_pct >= drop_threshold_pct:
            return {
                "alert": True,
                "current_price": current_price,
                "predicted_low": round(predicted_min, 2),
                "drop_pct": round(drop_pct, 1),
                "expected_date": min_row["ds"].strftime("%d %b %Y"),
                "message": (
                    f"Price may drop by {drop_pct:.1f}% to "
                    f"rs{predicted_min:.0f} around {min_row['ds'].strftime('%d %b %Y')}."
                ),
            }
        return {"alert": False, "drop_pct": round(drop_pct, 1)}

    def build_price_history_from_reviews(self, reviews_df: pd.DataFrame) -> pd.DataFrame:
        """
        Build a price-history DataFrame from scraped review dates.
        Returns DataFrame with columns: ['date', 'price', 'product']
        """
        try:
            df = reviews_df.copy()
            df["price_clean"] = (
                df["Price"].astype(str)
                .str.replace("Rs", "", regex=False)
                .str.replace(",", "", regex=False)
                .str.strip()
            )
            df["price_clean"] = pd.to_numeric(df["price_clean"], errors="coerce")
            df["date"] = pd.to_datetime(df["Date"], errors="coerce")

            result = (
                df.dropna(subset=["price_clean", "date"])
                .groupby(["Product Name", "date"], as_index=False)["price_clean"]
                .mean()
                .rename(columns={"Product Name": "product", "price_clean": "price"})
            )
            return result

        except Exception as e:
            raise CustomException(e, sys)

    # ------------------------------------------------------------------
    # Private -- Prophet
    # ------------------------------------------------------------------

    def _forecast_prophet(self, df: pd.DataFrame) -> pd.DataFrame:
        from prophet import Prophet  # lazy -- heavy lib

        model = Prophet(
            daily_seasonality=False,
            weekly_seasonality=True,
            yearly_seasonality=False,
            changepoint_prior_scale=0.3,
            interval_width=0.80,
        )
        model.fit(df)
        future = model.make_future_dataframe(periods=self.forecast_days)
        forecast = model.predict(future)

        for col in ("yhat", "yhat_lower", "yhat_upper"):
            forecast[col] = forecast[col].clip(lower=0)

        return forecast[["ds", "yhat", "yhat_lower", "yhat_upper", "trend"]]

    # ------------------------------------------------------------------
    # Private -- Linear regression fallback
    # ------------------------------------------------------------------

    def _forecast_linear(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Fit a simple linear trend on historic prices and project forward.
        Confidence bands are +/- 1.5 std of residuals.
        """
        t0 = df["ds"].min()
        df = df.copy()
        df["t"] = (df["ds"] - t0).dt.days.astype(float)

        coeffs = np.polyfit(df["t"], df["y"], deg=1)
        slope, intercept = coeffs

        residuals = df["y"] - (slope * df["t"] + intercept)
        std = residuals.std() if len(residuals) > 1 else df["y"].std() * 0.1

        last_date = df["ds"].max()
        all_dates = pd.concat([
            df["ds"],
            pd.Series(pd.date_range(last_date + timedelta(days=1), periods=self.forecast_days))
        ]).reset_index(drop=True)

        t_all = (all_dates - t0).dt.days.astype(float)
        yhat = (slope * t_all + intercept).clip(lower=0)

        return pd.DataFrame({
            "ds": all_dates,
            "yhat": yhat,
            "yhat_lower": (yhat - 1.5 * std).clip(lower=0),
            "yhat_upper": yhat + 1.5 * std,
            "trend": yhat,
        })

    # ------------------------------------------------------------------
    # Private -- Prepare
    # ------------------------------------------------------------------

    @staticmethod
    def _prepare(df: pd.DataFrame) -> pd.DataFrame:
        """Rename to ds/y columns and clean."""
        df = df.copy()
        if "date" in df.columns:
            df = df.rename(columns={"date": "ds", "price": "y"})
        df["ds"] = pd.to_datetime(df["ds"], errors="coerce")
        df["y"] = pd.to_numeric(df["y"], errors="coerce")
        return df.dropna(subset=["ds", "y"]).sort_values("ds").reset_index(drop=True)