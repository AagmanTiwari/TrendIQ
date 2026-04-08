import pandas as pd
import streamlit as st
from dotenv import load_dotenv
load_dotenv()

from src.cloud_io import MongoIO
from src.constants import SESSION_PRODUCT_KEY
from src.data_report.generate_data_report import DashboardGenerator

st.set_page_config(
    page_title="Myntra Analysis",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Review Analysis Dashboard")

mongo_con = MongoIO()


def create_analysis_page(review_data: pd.DataFrame):
    if review_data is not None and not review_data.empty:
        with st.expander("📋 Raw Review Data", expanded=False):
            st.dataframe(review_data, use_container_width=True)

        if st.button("🚀 Generate Analysis"):
            dashboard = DashboardGenerator(review_data)
            dashboard.display_general_info()
            dashboard.display_product_sections()
    else:
        st.warning("No review data available.")


# Safely access session state
data_available = st.session_state.get("data", False)
product_name = st.session_state.get(SESSION_PRODUCT_KEY, None)

if data_available and product_name:
    try:
        data = mongo_con.get_reviews(product_name=product_name)
        create_analysis_page(data)
    except Exception as e:
        st.error(f"Error loading data from MongoDB: {e}")
else:
    st.info("💡 No data available for analysis. Please go to the **Search page** and scrape some reviews first.")
    with st.sidebar:
        st.markdown("### 👈 Go to Search Page")
        st.markdown("Use the main page to scrape reviews before viewing analysis here.")