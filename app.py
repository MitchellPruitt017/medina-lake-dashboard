import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

st.set_page_config(page_title="Texas Water Dashboard", layout="wide")

st.title("Texas Water Dashboard")
st.subheader("Medina Lake MVP")

st.write("Live public water data for Medina Lake and its watershed.")
local_tz = ZoneInfo("America/Chicago")

# Medina Lake USGS site ID
site_id = "08179500"

url = (
    "https://api.waterdata.usgs.gov/ogcapi/v0/collections/continuous/items"
    f"?f=json&monitoring_location_id=USGS-{site_id}&parameter_code=62614&time=P30D&limit=50000"
)

response = requests.get(url, timeout=10)
data = response.json()

site_name = "Medina Lk nr San Antonio, TX"

clean_readings = []

for feature in data["features"]:
    properties = feature["properties"]

    clean_readings.append({
        "value": float(properties["value"]),
        "time": datetime.fromisoformat(properties["time"])
    })

clean_readings.sort(key=lambda x: x["time"])

latest = clean_readings[-1]
unit = "ft"


def get_change(hours_back):
    target_time = latest["time"] - timedelta(hours=hours_back)

    past_reading = min(
        clean_readings,
        key=lambda x: abs(x["time"] - target_time)
    )

    return latest["value"] - past_reading["value"]


change_24h = get_change(24)
change_7d = get_change(24 * 7)
change_30d = get_change(24 * 30)

if change_24h > 0.05:
    trend = "📈 Rising"
elif change_24h < -0.05:
    trend = "📉 Falling"
else:
    trend = "➡️ Stable"

col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.metric(
        label="Current Elevation",
        value=f"{latest['value']:.2f} {unit}"
    )

with col2:
    st.metric(
        label="24-Hour Change",
        value=f"{change_24h:+.2f} {unit}"
    )

with col3:
    st.metric(
        label="7-Day Change",
        value=f"{change_7d:+.2f} {unit}"
    )

with col4:
    st.metric(
        label="30-Day Change",
        value=f"{change_30d:+.2f} {unit}"
    )

with col5:
    st.metric(
        label="Trend",
        value=trend
    )

st.caption(f"{site_name} · Last reading: {latest['time'].astimezone(local_tz).strftime('%b %d, %Y at %#I:%M %p %Z')}")

st.divider()

st.subheader("30-Day Lake Elevation Trend")

chart_data = pd.DataFrame(clean_readings)

chart_data = chart_data.rename(columns={
    "time": "Time",
    "value": "Elevation"
})

y_min = chart_data["Elevation"].min() - 1
y_max = chart_data["Elevation"].max() + 1

fig = px.line(
    chart_data,
    x="Time",
    y="Elevation",
    title="Medina Lake Elevation - Last 30 Days"
)

fig.update_yaxes(range=[y_min, y_max], title="Elevation (ft)")
fig.update_xaxes(title="Date")

fig.update_layout(
    dragmode=False
)

st.plotly_chart(
    fig,
    use_container_width=True,
    config={
        "displayModeBar": False,
        "scrollZoom": False
    }
)

st.divider()

st.subheader("Lake Level Simulator")

st.write(
    "Pick a lake elevation to estimate Medina Lake's surface area and stored water volume."
)

twdb_url = "https://www.twdb.texas.gov/hydro_survey/medina/1995-07/elev_area_vol.txt"

@st.cache_data
def load_medina_capacity_table():
    response = requests.get(twdb_url, timeout=10)
    lines = response.text.splitlines()

    rows = []

    for line in lines:
        parts = line.split()

        if len(parts) >= 3:
            try:
                elevation = float(parts[0])
                area = float(parts[1].replace(",", ""))
                volume = float(parts[2].replace(",", ""))

                rows.append({
                    "Elevation": elevation,
                    "Surface Area": area,
                    "Volume": volume
                })
            except ValueError:
                pass

    return pd.DataFrame(rows)

capacity_df = load_medina_capacity_table()

if capacity_df.empty:
    st.warning("Could not load the TWDB Medina Lake elevation-area-volume table.")
else:
    capacity_df = capacity_df.sort_values("Elevation")

    min_elevation = float(capacity_df["Elevation"].min())
    max_elevation = float(capacity_df["Elevation"].max())

    selected_elevation = st.slider(
        "Lake elevation",
        min_value=min_elevation,
        max_value=max_elevation,
        value=float(round(latest["value"], 1)),
        step=0.1,
        format="%.1f ft"
    )

    area_lookup = pd.Series(
        capacity_df["Surface Area"].values,
        index=capacity_df["Elevation"]
    )

    volume_lookup = pd.Series(
        capacity_df["Volume"].values,
        index=capacity_df["Elevation"]
    )

    area_lookup = area_lookup[~area_lookup.index.duplicated(keep="first")]
    volume_lookup = volume_lookup[~volume_lookup.index.duplicated(keep="first")]

    area_lookup = area_lookup.reindex(
        area_lookup.index.union([selected_elevation])
    ).sort_index().interpolate(method="index")

    volume_lookup = volume_lookup.reindex(
        volume_lookup.index.union([selected_elevation])
    ).sort_index().interpolate(method="index")

    estimated_area = float(area_lookup.loc[selected_elevation])
    estimated_volume = float(volume_lookup.loc[selected_elevation])

    conservation_pool = 1064.2

    full_pool_lookup = volume_lookup.reindex(
        volume_lookup.index.union([conservation_pool])
    ).sort_index().interpolate(method="index")

    full_pool_volume = float(full_pool_lookup.loc[conservation_pool])

    percent_full = estimated_volume / full_pool_volume * 100

    sim_col1, sim_col2, sim_col3 = st.columns(3)

    with sim_col1:
        st.metric(
            label="Selected Elevation",
            value=f"{selected_elevation:.1f} ft"
        )

    with sim_col2:
        st.metric(
            label="Estimated Surface Area",
            value=f"{estimated_area:,.0f} acres"
        )

    with sim_col3:
        st.metric(
            label="Estimated Storage",
            value=f"{estimated_volume:,.0f} acre-ft",
            help=f"Approximately {percent_full:.1f}% of conservation pool storage."
        )

    simulator_chart = px.line(
        capacity_df,
        x="Elevation",
        y="Volume",
        title="Medina Lake Storage by Elevation"
    )

    simulator_chart.add_vline(
        x=selected_elevation,
        line_dash="dash",
        annotation_text=f"{selected_elevation:.1f} ft",
        annotation_position="top"
    )

    simulator_chart.update_yaxes(title="Volume (acre-ft)")
    simulator_chart.update_xaxes(title="Elevation (ft)")

    simulator_chart.update_layout(
        dragmode=False,
        height=350
    )

    st.plotly_chart(
        simulator_chart,
        use_container_width=True,
        config={
            "displayModeBar": False,
            "scrollZoom": False
        }
    )

st.caption(
    "Simulator uses the TWDB 1995 Medina Lake elevation-area-volume table. "
    "Elevations are in NGVD29, matching the Medina Lake gauge datum."
)

st.divider()

st.subheader("Upstream Gauge")

river_site_id = "08178980"

river_url = (
    "https://api.waterdata.usgs.gov/ogcapi/v0/collections/continuous/items"
    f"?f=json&monitoring_location_id=USGS-{river_site_id}&parameter_code=00060&time=P2D&limit=50000"
)

river_response = requests.get(river_url, timeout=10)
river_data = river_response.json()

river_site_name = "Medina Rv abv English Crsg nr Pipe Creek, TX"

river_readings = []

for feature in river_data["features"]:
    properties = feature["properties"]

    river_readings.append({
        "value": float(properties["value"]),
        "time": datetime.fromisoformat(properties["time"])
    })

river_readings.sort(key=lambda x: x["time"])

river_latest = river_readings[-1]
river_flow = river_latest["value"]
river_reading_time = river_latest["time"]
river_unit = "cfs"

river_target_time = river_latest["time"] - timedelta(hours=24)

river_reading_24h_ago = min(
    river_readings,
    key=lambda x: abs(x["time"] - river_target_time)
)

river_change_24h = river_latest["value"] - river_reading_24h_ago["value"]

if river_change_24h > 10:
    river_trend = "📈 Rising"
elif river_change_24h < -10:
    river_trend = "📉 Falling"
else:
    river_trend = "➡️ Stable"

river_col1, river_col2, river_col3 = st.columns(3)

with river_col1:
    st.metric(
        label="Medina River Flow at English Crossing",
        value=f"{river_flow:,.0f} {river_unit}"
    )

with river_col2:
    st.metric(
        label="24-Hour Flow Change",
        value=f"{river_change_24h:+,.0f} {river_unit}"
    )

with river_col3:
    st.metric(
        label="River Trend",
        value=river_trend
    )

st.caption(f"{river_site_name} · Last reading: {river_reading_time.astimezone(local_tz).strftime('%b %d, %Y at %#I:%M %p %Z')}")

st.divider()

st.subheader("Watershed Summary")

if trend == "📈 Rising" and river_trend == "📈 Rising":
    summary = "Medina Lake is rising, and the Medina River at English Crossing is also rising. Runoff is still actively moving toward the lake."

elif trend == "📈 Rising" and river_trend == "📉 Falling":
    summary = "Medina Lake is rising, but river flows are falling. The lake may still be responding to earlier runoff."

elif trend == "📉 Falling" and river_trend == "📈 Rising":
    summary = "The lake is falling, but river flows are rising. Incoming runoff may begin affecting lake levels soon."

elif trend == "📉 Falling" and river_trend == "📉 Falling":
    summary = "Both lake levels and river flows are falling. Watershed inflows appear to be slowing."

else:
    summary = "Conditions are relatively stable based on the latest observations."

st.info(summary)

st.divider()

st.subheader("Watershed Rain Index")

rain_locations = [
    {"name": "North Prong Medina River", "lat": 29.8759, "lon": -99.3485},
    {"name": "City of Medina", "lat": 29.8001, "lon": -99.2416},
    {"name": "City of Bandera", "lat": 29.7277, "lon": -99.0714},
    {"name": "City of Pipe Creek", "lat": 29.7236, "lon": -98.9359},
    {"name": "Medina Lake", "lat": 29.5402, "lon": -98.9339},
]

rain_location_results = []

for location in rain_locations:
    rain_url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={location['lat']}&longitude={location['lon']}"
        "&hourly=precipitation"
        "&past_days=7"
        "&forecast_days=1"
        "&timezone=America%2FChicago"
    )

    rain_response = requests.get(rain_url, timeout=10)
    rain_data = rain_response.json()

    rain_times = rain_data["hourly"]["time"]
    rain_values = rain_data["hourly"]["precipitation"]

    rain_readings = []

    for time_text, precip in zip(rain_times, rain_values):
        rain_readings.append({
            "time": datetime.fromisoformat(time_text),
            "precip": float(precip)
        })

    now = rain_readings[-1]["time"]

    rain_24h_mm = sum(
        reading["precip"]
        for reading in rain_readings
        if reading["time"] >= now - timedelta(hours=24)
    )

    rain_7d_mm = sum(
        reading["precip"]
        for reading in rain_readings
        if reading["time"] >= now - timedelta(days=7)
    )

    rain_location_results.append({
        "Location": location["name"],
        "Rainfall - Last 24 Hours": rain_24h_mm / 25.4,
        "Rainfall - Last 7 Days": rain_7d_mm / 25.4
    })

rain_results_df = pd.DataFrame(rain_location_results)

watershed_rain_24h = rain_results_df["Rainfall - Last 24 Hours"].mean()
watershed_rain_7d = rain_results_df["Rainfall - Last 7 Days"].mean()

wettest_24h_row = rain_results_df.loc[
    rain_results_df["Rainfall - Last 24 Hours"].idxmax()
]

rain_col1, rain_col2, rain_col3 = st.columns(3)

with rain_col1:
    st.metric(
        label="Avg Watershed Rain - Last 24 Hours",
        value=f"{watershed_rain_24h:.2f} in"
    )

with rain_col2:
    st.metric(
        label="Avg Watershed Rain - Last 7 Days",
        value=f"{watershed_rain_7d:.2f} in"
    )

with rain_col3:
    st.metric(
        label="Wettest Spot - Last 24 Hours",
        value=f"{wettest_24h_row['Rainfall - Last 24 Hours']:.2f} in",
        help=f"{wettest_24h_row['Location']} had the highest estimated rainfall over the last 24 hours."
    )

rain_display_df = rain_results_df.copy()

rain_display_df["Rainfall - Last 24 Hours"] = rain_display_df[
    "Rainfall - Last 24 Hours"
].apply(lambda value: f"{value:.2f} in")

rain_display_df["Rainfall - Last 7 Days"] = rain_display_df[
    "Rainfall - Last 7 Days"
].apply(lambda value: f"{value:.2f} in")

rain_table_col, rain_map_col = st.columns([1, 1])

with rain_table_col:
    st.dataframe(
        rain_display_df,
        hide_index=True,
        width=500
    )

with rain_map_col:

    st.markdown("**Watershed Rainfall Map**")

    map_points_df = pd.DataFrame(rain_locations)

    watershed_outline = pd.DataFrame({
        "lat": [29.95, 29.88, 29.78, 29.66, 29.54, 29.58, 29.72, 29.86, 29.95],
        "lon": [-99.42, -99.20, -99.07, -98.98, -98.93, -99.03, -99.18, -99.36, -99.42]
    })

    map_fig = go.Figure()

    map_fig.add_trace(go.Scattermapbox(
        lat=watershed_outline["lat"],
        lon=watershed_outline["lon"],
        mode="lines",
        name="Approximate Medina Lake Watershed",
        line=dict(width=3)
    ))

    map_fig.add_trace(go.Scattermapbox(
        lat=map_points_df["lat"],
        lon=map_points_df["lon"],
        mode="markers+text",
        text=map_points_df["name"],
        textposition="top right",
        marker=dict(size=12),
        name="Rainfall points"
    ))

    map_fig.update_layout(
        mapbox=dict(
            style="open-street-map",
            center=dict(lat=29.75, lon=-99.16),
            zoom=9.0
        ),
        height=450,
        margin=dict(l=0, r=0, t=30, b=0),
        dragmode=False
    )

    st.plotly_chart(
        map_fig,
        use_container_width=True,
        config={
            "displayModeBar": False,
            "scrollZoom": False
        }
    )

st.caption("Watershed rain index uses five representative points: North Prong Medina River, Medina, Bandera, Pipe Creek, and Medina Lake. Values are Open-Meteo estimates and should be treated as approximate.")

st.divider()

st.subheader("7-Day Watershed Rainfall Forecast")

forecast_location_results = []
forecast_daily_rows = []

for location in rain_locations:
    forecast_url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={location['lat']}&longitude={location['lon']}"
        "&daily=precipitation_sum,precipitation_probability_max"
        "&forecast_days=8"
        "&timezone=America%2FChicago"
    )

    forecast_response = requests.get(forecast_url, timeout=10)
    forecast_data = forecast_response.json()

    forecast_dates = forecast_data["daily"]["time"][1:]
    forecast_precip_mm = forecast_data["daily"]["precipitation_sum"][1:]
    forecast_probability = forecast_data["daily"]["precipitation_probability_max"][1:]

    forecast_precip_inches = [
        value / 25.4 for value in forecast_precip_mm
    ]

    forecast_total = sum(forecast_precip_inches)

    max_probability_index = forecast_probability.index(max(forecast_probability))
    forecast_max_probability = forecast_probability[max_probability_index]
    forecast_max_probability_date = pd.to_datetime(
        forecast_dates[max_probability_index]
    ).strftime("%B %d, %Y")

    forecast_location_results.append({
        "Location": location["name"],
        "Expected Rainfall - Next 7 Days": forecast_total,
        "Highest Daily Rain Chance": forecast_max_probability,
        "Highest Rain Chance Date": forecast_max_probability_date
    })

    for date, precip_inches, probability in zip(
        forecast_dates,
        forecast_precip_inches,
        forecast_probability
    ):
        forecast_daily_rows.append({
            "Date": date,
            "Location": location["name"],
            "Forecast Rainfall": precip_inches,
            "Rain Chance": probability
        })

forecast_results_df = pd.DataFrame(forecast_location_results)
forecast_daily_df = pd.DataFrame(forecast_daily_rows)

watershed_forecast_total = forecast_results_df[
    "Expected Rainfall - Next 7 Days"
].mean()

max_forecast_row = forecast_results_df.loc[
    forecast_results_df["Highest Daily Rain Chance"].idxmax()
]

forecast_col1, forecast_col2 = st.columns(2)

with forecast_col1:
    st.metric(
        label="Avg Expected Watershed Rain - Next 7 Days",
        value=f"{watershed_forecast_total:.2f} in"
    )

with forecast_col2:
    st.metric(
        label="Highest Daily Rain Chance",
        value=f"{max_forecast_row['Highest Daily Rain Chance']:.0f}% on {max_forecast_row['Highest Rain Chance Date']}",
        help=f"Highest daily rain chance among the five watershed points, occurring near {max_forecast_row['Location']}."
    )

forecast_display_df = forecast_results_df.copy()

forecast_display_df["Expected Rainfall - Next 7 Days"] = forecast_display_df[
    "Expected Rainfall - Next 7 Days"
].apply(lambda value: f"{value:.2f} in")

forecast_display_df["Highest Daily Rain Chance"] = forecast_display_df[
    "Highest Daily Rain Chance"
].apply(lambda value: f"{value:.0f}%")

forecast_display_df = forecast_display_df.rename(columns={
    "Highest Rain Chance Date": "Rain Chance Date"
})

forecast_table_col, forecast_chart_col = st.columns([1, 1.4])

with forecast_table_col:
    st.dataframe(
        forecast_display_df,
        hide_index=True,
        width=650
    )

daily_avg_forecast = forecast_daily_df.groupby("Date", as_index=False)[
    "Forecast Rainfall"
].mean()

daily_avg_forecast["Date"] = pd.to_datetime(
    daily_avg_forecast["Date"]
).dt.strftime("%B %d, %Y")

with forecast_chart_col:
    if daily_avg_forecast["Forecast Rainfall"].sum() == 0:
        st.info("No measurable rainfall is currently forecast across the watershed for the next 7 days.")

    forecast_fig = px.bar(
        daily_avg_forecast,
        x="Date",
        y="Forecast Rainfall",
        title="Average Daily Watershed Rainfall Forecast"
    )

    forecast_fig.update_yaxes(title="Rainfall (in)")
    forecast_fig.update_xaxes(title="Date")

    forecast_fig.update_layout(
        dragmode=False,
        height=300
    )

    st.plotly_chart(
        forecast_fig,
        use_container_width=True,
        config={
            "displayModeBar": False,
            "scrollZoom": False
        }
    )

st.caption("Forecast uses the average of five representative watershed points. This is a simple index, not an official hydrologic forecast.")