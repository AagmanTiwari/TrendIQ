import streamlit as st
import pandas as pd
import plotly.express as px
import sys
import logging

from src.exception import CustomException

logger = logging.getLogger(__name__)


class DashboardGenerator:
    def __init__(self, data: pd.DataFrame):
        self.data = self._preprocess(data.copy())

    def _preprocess(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean and cast columns to correct types."""
        df["Over_All_Rating"] = pd.to_numeric(df["Over_All_Rating"], errors="coerce")
        df["Rating"] = pd.to_numeric(df["Rating"], errors="coerce")
        df["Price"] = pd.to_numeric(
            df["Price"].astype(str).str.replace("₹", "", regex=False).str.strip(),
            errors="coerce"
        )
        return df

    def display_general_info(self):
        st.header("📊 General Information")

        col1, col2 = st.columns(2)

        with col1:
            product_ratings = (
                self.data.groupby("Product Name", as_index=False)["Over_All_Rating"]
                .mean()
                .dropna()
            )
            fig_pie = px.pie(
                product_ratings,
                values="Over_All_Rating",
                names="Product Name",
                title="Average Ratings by Product",
                hole=0.3,
            )
            st.plotly_chart(fig_pie, use_container_width=True)

        with col2:
            avg_prices = (
                self.data.groupby("Product Name", as_index=False)["Price"]
                .mean()
                .dropna()
            )
            fig_bar = px.bar(
                avg_prices,
                x="Product Name",
                y="Price",
                color="Product Name",
                title="Average Price Comparison",
                color_discrete_sequence=px.colors.qualitative.Bold,
                text_auto=".2s",
            )
            fig_bar.update_xaxes(title="Product Name")
            fig_bar.update_yaxes(title="Average Price (₹)")
            fig_bar.update_layout(showlegend=False)
            st.plotly_chart(fig_bar, use_container_width=True)

        # Rating distribution across all products
        fig_hist = px.histogram(
            self.data.dropna(subset=["Rating"]),
            x="Rating",
            color="Product Name",
            barmode="overlay",
            title="Rating Distribution Across Products",
            nbins=10,
            opacity=0.75,
        )
        st.plotly_chart(fig_hist, use_container_width=True)

    def display_product_sections(self):
        st.header("🧾 Product Sections")

        product_names = self.data["Product Name"].unique()

        for product_name in product_names:
            product_data = self.data[self.data["Product Name"] == product_name]

            with st.expander(f"📦 {product_name}", expanded=True):
                m1, m2, m3 = st.columns(3)
                m1.metric("💰 Avg Price", f"₹{product_data['Price'].mean():.2f}")
                m2.metric("⭐ Avg Rating", f"{product_data['Over_All_Rating'].mean():.2f}")
                m3.metric("💬 Total Reviews", len(product_data))

                col_pos, col_neg = st.columns(2)

                with col_pos:
                    st.subheader("✨ Top Positive Reviews")
                    positive = product_data[product_data["Rating"] >= 4.5].nlargest(5, "Rating")
                    if positive.empty:
                        st.info("No highly positive reviews found.")
                    for _, row in positive.iterrows():
                        st.markdown(f"**⭐ {row['Rating']}** — {row['Comment']}")

                with col_neg:
                    st.subheader("💢 Top Negative Reviews")
                    negative = product_data[product_data["Rating"] <= 2].nsmallest(5, "Rating")
                    if negative.empty:
                        st.info("No highly negative reviews found.")
                    for _, row in negative.iterrows():
                        st.markdown(f"**⭐ {row['Rating']}** — {row['Comment']}")

                st.subheader("📈 Rating Breakdown")
                rating_counts = (
                    product_data["Rating"]
                    .value_counts()
                    .reset_index()
                    .rename(columns={"index": "Rating", "Rating": "Count"})
                    .sort_values("Rating", ascending=False)
                )
                fig_rc = px.bar(
                    rating_counts,
                    x="Rating",
                    y="Count",
                    color="Rating",
                    title=f"Rating Counts — {product_name}",
                    color_continuous_scale="RdYlGn",
                )
                st.plotly_chart(fig_rc, use_container_width=True)