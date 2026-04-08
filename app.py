"""
app.py  —  TrendIQ: Real-Time Retail Intelligence Scraper
Run with:  streamlit run app.py
"""
import streamlit as st
from dotenv import load_dotenv
load_dotenv()

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from src.cloud_io import MongoIO
from src.constants import SESSION_PRODUCT_KEY
from src.scrapper import get_scraper, SCRAPERS
from src.sentiment.analyser import SentimentAnalyser
from src.forecasting.price_forecaster import PriceForecaster
from src.alerts.emailer import PriceAlertEmailer

st.set_page_config(page_title="TrendIQ", page_icon="📊", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
.metric-card{background:var(--background-color,#f8f9fa);border-radius:12px;padding:16px 20px;border-left:4px solid;margin-bottom:8px;}
.positive{border-color:#2a9d8f;}.negative{border-color:#e76f51;}.neutral{border-color:#e9c46a;}
.alert-box{background:#fff3cd;border:1px solid #ffc107;border-radius:10px;padding:16px;margin:12px 0;}
</style>""", unsafe_allow_html=True)

PLATFORM_COLORS = {"Myntra":"#ff3f6c","Amazon":"#ff9900","Flipkart":"#2874f0","Meesho":"#9b2d8e"}

for key, default in [("data",False),("enriched_df",None),(SESSION_PRODUCT_KEY,""),("alert_email",""),("selected_platforms",["Myntra"])]:
    if key not in st.session_state:
        st.session_state[key] = default

with st.sidebar:
    st.markdown("## 📊 TrendIQ")
    st.divider()
    st.markdown("### 🛒 Platforms")
    platform_selection = []
    for name in SCRAPERS.keys():
        label = name.capitalize()
        if st.checkbox(label, value=(label in st.session_state["selected_platforms"])):
            platform_selection.append(label)
    st.session_state["selected_platforms"] = platform_selection
    st.divider()
    st.markdown("### ⚙️ Settings")
    alert_email = st.text_input("📧 Alert email", placeholder="your@email.com", value=st.session_state["alert_email"])
    st.session_state["alert_email"] = alert_email
    drop_threshold = st.slider("Drop alert threshold (%)", 5, 30, 10)
    forecast_days = st.slider("Forecast horizon (days)", 7, 90, 30, step=7)

st.title("📊 TrendIQ — Real-Time Retail Intelligence")
st.caption("Multi-platform scraping · Sentiment analysis · Price forecasting · Drop alerts")
st.divider()

tab_scrape, tab_compare, tab_sentiment, tab_forecast, tab_raw = st.tabs([
    "🔍 Scrape","⚖️ Platform Comparison","💬 Sentiment","📈 Price Forecast","📋 Raw Data"
])

# ── TAB 1: Scrape ─────────────────────────────────────────────────────────────
with tab_scrape:
    st.subheader("Search & Scrape Across Platforms")
    if not platform_selection:
        st.warning("Select at least one platform in the sidebar.")
        st.stop()

    with st.form("scrape_form"):
        c1, c2 = st.columns([3,1])
        product = c1.text_input("🔍 Product name", placeholder="e.g. blue denim jacket")
        no_of_products = c2.number_input("Products per platform", 1, 10, 2, step=1)
        submitted = st.form_submit_button("🚀 Scrape All Platforms", use_container_width=True)

    if submitted and product.strip():
        st.session_state[SESSION_PRODUCT_KEY] = product.strip()
        all_frames = []
        with st.status(f"Scraping **{product}** across {len(platform_selection)} platform(s)…", expanded=True) as status:
            try:
                for platform in platform_selection:
                    st.write(f"🕷️ Scraping **{platform}**…")
                    if platform.lower() == "amazon":
                        st.write("  ⚠️ **Amazon**: Review scraping is blocked by Amazon.in (authentication required for all review pages). Use [Amazon PA API](https://affiliate-program.amazon.in/assoc_credentials/home) for production access.")
                        continue
                    if platform.lower() == "meesho":
                        st.write("  ⚠️ **Meesho**: Blocked by Akamai bot protection (blocks both requests and real Chrome). Residential proxies required — not currently supported.")
                        continue
                    try:
                        scraper = get_scraper(platform=platform.lower(), product_name=product.strip(), no_of_products=int(no_of_products))
                        raw_df = scraper.get_review_data()
                        if raw_df is not None and not raw_df.empty:
                            all_frames.append(raw_df)
                            st.write(f"  ✅ {platform}: {len(raw_df)} reviews from {raw_df['Product Name'].nunique()} product(s).")
                        else:
                            st.write(f"  ⚠️ {platform}: No reviews found.")
                    except Exception as plat_err:
                        st.write(f"  ❌ {platform} failed: {plat_err}")

                if not all_frames:
                    status.update(label="No reviews found on any platform.", state="error")
                else:
                    combined = pd.concat(all_frames, axis=0, ignore_index=True)
                    st.write(f"💬 Running sentiment on {len(combined)} reviews…")
                    enriched = SentimentAnalyser().analyse(combined)
                    st.write("✅ Sentiment complete.")
                    st.write("💾 Storing to MongoDB…")
                    MongoIO().store_reviews(product_name=product.strip(), reviews=enriched)
                    st.write("✅ Stored.")
                    st.session_state["enriched_df"] = enriched
                    st.session_state["data"] = True
                    status.update(label="Done! Explore the tabs above.", state="complete")
            except Exception as e:
                status.update(label="Error.", state="error")
                st.error(f"❌ {e}")
    elif submitted:
        st.warning("Please enter a product name.")

    df = st.session_state.get("enriched_df")
    if df is not None:
        st.divider()
        c1,c2,c3,c4,c5 = st.columns(5)
        c1.metric("Total reviews", len(df))
        c2.metric("Platforms", df["Platform"].nunique() if "Platform" in df.columns else 1)
        c3.metric("Products", df["Product Name"].nunique())
        pos = (df.get("sentiment_label")=="Positive").mean()*100 if "sentiment_label" in df.columns else 0
        neg = (df.get("sentiment_label")=="Negative").mean()*100 if "sentiment_label" in df.columns else 0
        c4.metric("Positive %", f"{pos:.1f}%")
        c5.metric("Negative %", f"{neg:.1f}%")

# ── TAB 2: Platform Comparison ────────────────────────────────────────────────
with tab_compare:
    st.subheader("⚖️ Cross-Platform Comparison")
    df = st.session_state.get("enriched_df")
    if df is None or "Platform" not in df.columns:
        st.info("Scrape from multiple platforms to see comparisons here.")
    else:
        if "sentiment_label" in df.columns:
            sent_counts = df.groupby(["Platform","sentiment_label"]).size().reset_index(name="count")
            fig = px.bar(sent_counts, x="Platform", y="count", color="sentiment_label", barmode="group",
                color_discrete_map={"Positive":"#2a9d8f","Neutral":"#e9c46a","Negative":"#e76f51"},
                category_orders={"sentiment_label":["Positive","Neutral","Negative"]},
                title="Sentiment distribution per platform")
            st.plotly_chart(fig, use_container_width=True)

        if "sentiment_score" in df.columns:
            avg_sent = df.groupby("Platform")["sentiment_score"].mean().reset_index()
            fig2 = px.bar(avg_sent, x="Platform", y="sentiment_score", color="Platform",
                color_discrete_map=PLATFORM_COLORS, title="Avg sentiment score by platform", text_auto=".2f")
            fig2.update_layout(showlegend=False, yaxis_range=[0,1])
            st.plotly_chart(fig2, use_container_width=True)

        price_df = df.copy()
        price_df["Price_num"] = price_df["Price"].astype(str).str.replace("₹","",regex=False).str.replace(",","",regex=False).str.strip().pipe(pd.to_numeric,errors="coerce")
        if not price_df.dropna(subset=["Price_num"]).empty:
            fig3 = px.box(price_df.dropna(subset=["Price_num"]), x="Platform", y="Price_num", color="Platform",
                color_discrete_map=PLATFORM_COLORS, title="Price distribution by platform (₹)", points="outliers")
            fig3.update_layout(showlegend=False, yaxis_title="Price (₹)")
            st.plotly_chart(fig3, use_container_width=True)

        vol = df.groupby("Platform").size().reset_index(name="Reviews")
        fig4 = px.pie(vol, values="Reviews", names="Platform", color="Platform",
            color_discrete_map=PLATFORM_COLORS, title="Review volume per platform", hole=0.4)
        st.plotly_chart(fig4, use_container_width=True)

        if "vader_compound" in df.columns:
            fig5 = px.violin(df, x="Platform", y="vader_compound", color="Platform", box=True, points="outliers",
                color_discrete_map=PLATFORM_COLORS, title="VADER score distribution by platform")
            fig5.add_hline(y=0.05, line_dash="dash", line_color="green", annotation_text="Positive")
            fig5.add_hline(y=-0.05, line_dash="dash", line_color="red", annotation_text="Negative")
            fig5.update_layout(showlegend=False)
            st.plotly_chart(fig5, use_container_width=True)

        st.divider()
        st.markdown("#### Sample reviews by platform")
        platforms = df["Platform"].unique().tolist()
        cols = st.columns(len(platforms))
        for i, plat in enumerate(platforms):
            with cols[i]:
                st.markdown(f"**{plat}**")
                for _, row in df[df["Platform"]==plat].head(3).iterrows():
                    icon = "🟢" if row.get("sentiment_label")=="Positive" else "🔴" if row.get("sentiment_label")=="Negative" else "🟡"
                    st.markdown(f"{icon} _{row['Comment'][:120]}…_")
                    st.caption(f"⭐ {row['Rating']} | {row['Name']}")
                    st.divider()

# ── TAB 3: Sentiment ──────────────────────────────────────────────────────────
with tab_sentiment:
    st.subheader("💬 Sentiment Intelligence")
    df = st.session_state.get("enriched_df")
    if df is None or "sentiment_label" not in df.columns:
        st.info("Scrape some products first.")
    else:
        summary = SentimentAnalyser().summarise(df)
        st.markdown("#### Sentiment by product")
        cols = st.columns(min(len(summary), 3))
        for i, (prod, stats) in enumerate(summary.items()):
            short = prod[:40]+"…" if len(prod)>40 else prod
            score = stats["avg_sentiment_score"]
            card_class = "positive" if score>0.6 else "negative" if score<0.4 else "neutral"
            with cols[i%3]:
                st.markdown(f"<div class='metric-card {card_class}'><b>{short}</b><br>✅ {stats['positive']} pos &nbsp; ❌ {stats['negative']} neg &nbsp; ➖ {stats['neutral']} neutral<br>Score: <b>{score:.2f}</b></div>", unsafe_allow_html=True)

        st.divider()
        fig2 = px.scatter(df, x="tb_subjectivity", y="tb_polarity", color="sentiment_label",
            symbol="Platform" if "Platform" in df.columns else None,
            hover_data=["Product Name","Comment"],
            color_discrete_map={"Positive":"#2a9d8f","Neutral":"#e9c46a","Negative":"#e76f51"},
            title="Subjectivity vs polarity (TextBlob)", opacity=0.65)
        fig2.add_hline(y=0, line_dash="dot", line_color="gray")
        st.plotly_chart(fig2, use_container_width=True)

        cp, cn = st.columns(2)
        with cp:
            st.markdown("#### ✅ Top positive")
            for _, row in df[df["sentiment_label"]=="Positive"].nlargest(5,"vader_compound").iterrows():
                st.success(f"[{row.get('Platform','')}] ⭐{row.get('Rating','N/A')} — {row['Comment'][:180]}")
        with cn:
            st.markdown("#### ❌ Top negative")
            for _, row in df[df["sentiment_label"]=="Negative"].nsmallest(5,"vader_compound").iterrows():
                st.error(f"[{row.get('Platform','')}] ⭐{row.get('Rating','N/A')} — {row['Comment'][:180]}")

# ── TAB 4: Forecast ───────────────────────────────────────────────────────────
with tab_forecast:
    st.subheader("📈 Price Forecast & Drop Alerts")
    df = st.session_state.get("enriched_df")
    if df is None:
        st.info("Scrape some products first.")
    else:
        forecaster = PriceForecaster(forecast_days=forecast_days)
        price_history = forecaster.build_price_history_from_reviews(df)
        if price_history.empty:
            st.warning("Not enough date-stamped price data. Showing current prices.")
            price_df = df.copy()
            price_df["Price_num"] = price_df["Price"].astype(str).str.replace("₹","").str.replace(",","").str.strip().pipe(pd.to_numeric,errors="coerce")
            avg = price_df.groupby(["Platform","Product Name"])["Price_num"].mean().reset_index()
            fig = px.bar(avg, x="Product Name", y="Price_num", color="Platform", color_discrete_map=PLATFORM_COLORS, barmode="group", title="Avg price by product & platform", text_auto=".0f")
            st.plotly_chart(fig, use_container_width=True)
        else:
            for prod_name, grp in price_history.groupby("product"):
                st.markdown(f"#### {prod_name}")
                forecast_df = forecaster.forecast(grp, product_name=prod_name)
                if forecast_df.empty:
                    st.info(f"Not enough data for {prod_name}.")
                    continue
                try:
                    cp = float(df[df["Product Name"]==prod_name]["Price"].astype(str).str.replace("₹","").str.replace(",","").str.strip().pipe(pd.to_numeric,errors="coerce").dropna().iloc[-1])
                    alert = forecaster.check_drop_alert(forecast_df, cp, drop_threshold_pct=drop_threshold)
                    if alert.get("alert"):
                        st.markdown(f"<div class='alert-box'>🔔 <b>Price Drop Alert!</b> Predicted drop of <b>{alert['drop_pct']}%</b> — ₹{alert['current_price']:.0f} → ₹{alert['predicted_low']:.0f} by {alert['expected_date']}.</div>", unsafe_allow_html=True)
                except Exception:
                    pass
                historical = grp.rename(columns={"date":"ds","price":"y"})
                fig = go.Figure()
                future_mask = forecast_df["ds"] > historical["ds"].max()
                fig.add_trace(go.Scatter(x=pd.concat([forecast_df[future_mask]["ds"],forecast_df[future_mask]["ds"][::-1]]),y=pd.concat([forecast_df[future_mask]["yhat_upper"],forecast_df[future_mask]["yhat_lower"][::-1]]),fill="toself",fillcolor="rgba(42,157,143,0.15)",line=dict(color="rgba(255,255,255,0)"),name="Forecast range"))
                fig.add_trace(go.Scatter(x=historical["ds"],y=historical["y"],mode="lines+markers",name="Historical",line=dict(color="#264653",width=2),marker=dict(size=6)))
                fig.add_trace(go.Scatter(x=forecast_df[future_mask]["ds"],y=forecast_df[future_mask]["yhat"],mode="lines",name=f"{forecast_days}d forecast",line=dict(color="#2a9d8f",width=2,dash="dot")))
                fig.update_layout(title=f"Price trend — {prod_name[:50]}",xaxis_title="Date",yaxis_title="Price (₹)",hovermode="x unified",legend=dict(orientation="h",y=1.12))
                st.plotly_chart(fig, use_container_width=True)
                st.divider()

# ── TAB 5: Raw Data ───────────────────────────────────────────────────────────
with tab_raw:
    st.subheader("📋 Raw Enriched Data")
    df = st.session_state.get("enriched_df")
    if df is None:
        st.info("No data yet.")
    else:
        c1,c2,c3 = st.columns(3)
        sel_plat = c1.selectbox("Platform", ["All"]+([list(df["Platform"].unique())] if "Platform" in df.columns else []))
        sel_prod = c2.selectbox("Product", ["All"]+list(df["Product Name"].unique()))
        sel_sent = c3.selectbox("Sentiment", ["All"]+([list(df["sentiment_label"].unique())] if "sentiment_label" in df.columns else []))
        filtered = df.copy()
        if sel_plat != "All" and "Platform" in filtered.columns: filtered = filtered[filtered["Platform"]==sel_plat]
        if sel_prod != "All": filtered = filtered[filtered["Product Name"]==sel_prod]
        if sel_sent != "All" and "sentiment_label" in filtered.columns: filtered = filtered[filtered["sentiment_label"]==sel_sent]
        st.dataframe(filtered, use_container_width=True, height=500)
        st.download_button("📥 Download CSV", data=filtered.to_csv(index=False).encode("utf-8"),
            file_name=f"trendiq_{st.session_state.get(SESSION_PRODUCT_KEY,'data')}.csv", mime="text/csv")

# ── Monkey-patch: show Amazon warning in sidebar ──────────────────────────────
# (append to existing sidebar section)