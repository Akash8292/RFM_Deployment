from flask import Flask, render_template_string
import pandas as pd
from waitress import serve
import plotly.express as px
import plotly.io as pio
import plotly.graph_objects as go
from datetime import datetime

app = Flask(__name__)

# Load data and preprocess it
def preprocess_data():
    data = pd.read_csv("rfm_data.csv")

    # Convert 'PurchaseDate' to datetime
    data['PurchaseDate'] = pd.to_datetime(data['PurchaseDate'], errors='coerce')

    # Calculate Recency
    data['Recency'] = (datetime.now().date() - data['PurchaseDate'].dt.date).apply(lambda x: x.days)

    # Calculate Frequency
    frequency_data = data.groupby('CustomerID')['OrderID'].count().reset_index()
    frequency_data.rename(columns={'OrderID': 'Frequency'}, inplace=True)
    data = data.merge(frequency_data, on='CustomerID', how='left')

    # Calculate Monetary Value
    monetary_data = data.groupby('CustomerID')['TransactionAmount'].sum().reset_index()
    monetary_data.rename(columns={'TransactionAmount': 'MonetaryValue'}, inplace=True)
    data = data.merge(monetary_data, on='CustomerID', how='left')

    # Define scoring criteria for each RFM value
    recency_scores = [5, 4, 3, 2, 1]  # Higher score for lower recency (more recent)
    frequency_scores = [1, 2, 3, 4, 5]  # Higher score for higher frequency
    monetary_scores = [1, 2, 3, 4, 5]  # Higher score for higher monetary value

    # Calculate RFM scores
    data['RecencyScore'] = pd.cut(data['Recency'], bins=5, labels=recency_scores)
    data['FrequencyScore'] = pd.cut(data['Frequency'], bins=5, labels=frequency_scores)
    data['MonetaryScore'] = pd.cut(data['MonetaryValue'], bins=5, labels=monetary_scores)

    # Convert RFM scores to numeric type
    data['RecencyScore'] = data['RecencyScore'].astype(int)
    data['FrequencyScore'] = data['FrequencyScore'].astype(int)
    data['MonetaryScore'] = data['MonetaryScore'].astype(int)

    # Calculate RFM score by combining the individual scores
    data['RFM_Score'] = data['RecencyScore'] + data['FrequencyScore'] + data['MonetaryScore']

    # Create RFM segments based on the RFM score
    segment_labels = ['Low-Value', 'Mid-Value', 'High-Value']
    data['Value Segment'] = pd.cut(data['RFM_Score'], bins=3, labels=segment_labels)

    # Create a new column for RFM Customer Segments
    data['RFM Customer Segments'] = ''
    data.loc[data['RFM_Score'] >= 9, 'RFM Customer Segments'] = 'Champions'
    data.loc[(data['RFM_Score'] >= 6) & (data['RFM_Score'] < 9), 'RFM Customer Segments'] = 'Potential Loyalists'
    data.loc[(data['RFM_Score'] >= 5) & (data['RFM_Score'] < 6), 'RFM Customer Segments'] = 'At Risk Customers'
    data.loc[(data['RFM_Score'] >= 4) & (data['RFM_Score'] < 5), 'RFM Customer Segments'] = "Can't Lose"
    data.loc[(data['RFM_Score'] >= 3) & (data['RFM_Score'] < 4), 'RFM Customer Segments'] = "Lost"

    return data

def fig_to_html(fig):
    return pio.to_html(fig, full_html=False)

def create_plots(data):
    pastel_colors = px.colors.qualitative.Pastel

    # RFM Segment Distribution
    segment_counts = data['Value Segment'].value_counts().reset_index()
    segment_counts.columns = ['Value Segment', 'Count']
    fig_segment_dist = px.bar(segment_counts, x='Value Segment', y='Count', color='Value Segment', color_discrete_sequence=pastel_colors, title='RFM Value Segment Distribution')
    fig_segment_dist.update_layout(xaxis_title='RFM Value Segment', yaxis_title='Count', showlegend=False)

    # RFM Customer Segments Comparison
    segment_counts = data['RFM Customer Segments'].value_counts()
    fig_rfm_segments = go.Figure(data=[go.Bar(x=segment_counts.index, y=segment_counts.values, marker=dict(color=pastel_colors))])
    champions_color = 'rgb(158, 202, 225)'
    fig_rfm_segments.update_traces(marker_color=[champions_color if segment == 'Champions' else pastel_colors[i]
                                                 for i, segment in enumerate(segment_counts.index)],
                                   marker_line_color='rgb(8, 48, 107)',
                                   marker_line_width=1.5, opacity=0.6)
    fig_rfm_segments.update_layout(title='Comparison of RFM Segments',
                                   xaxis_title='RFM Segments',
                                   yaxis_title='Number of Customers',
                                   showlegend=False)

    # Segment Scores Comparison
    segment_scores = data.groupby('RFM Customer Segments')[['RecencyScore', 'FrequencyScore', 'MonetaryScore']].mean().reset_index()
    fig_segment_scores = go.Figure()
    fig_segment_scores.add_trace(go.Bar(x=segment_scores['RFM Customer Segments'], y=segment_scores['RecencyScore'], name='Recency Score', marker_color='rgb(158,202,225)'))
    fig_segment_scores.add_trace(go.Bar(x=segment_scores['RFM Customer Segments'], y=segment_scores['FrequencyScore'], name='Frequency Score', marker_color='rgb(94,158,217)'))
    fig_segment_scores.add_trace(go.Bar(x=segment_scores['RFM Customer Segments'], y=segment_scores['MonetaryScore'], name='Monetary Score', marker_color='rgb(32,102,148)'))
    fig_segment_scores.update_layout(title='Comparison of RFM Segments based on Recency, Frequency, and Monetary Scores',
                                      xaxis_title='RFM Segments',
                                      yaxis_title='Score',
                                      barmode='group',
                                      showlegend=True)

    # New Distribution of RFM Segments after Re-engagement
    reactivation_rate = 0.2  # Assume 20% of lost customers can be re-engaged
    lost_customers = data[data['RFM Customer Segments'] == "Lost"]
    reactivated_customers = lost_customers.sample(frac=reactivation_rate, random_state=1)
    data.loc[reactivated_customers.index, 'RFM Customer Segments'] = 'Potential Loyalists'
    new_segment_counts = data['RFM Customer Segments'].value_counts()
    fig_new_segment_dist = go.Figure(data=[go.Bar(x=new_segment_counts.index, y=new_segment_counts.values, marker=dict(color=pastel_colors))])
    fig_new_segment_dist.update_layout(title='New Distribution of RFM Segments after Re-engagement',
                                       xaxis_title='RFM Segments',
                                       yaxis_title='Number of Customers',
                                       showlegend=False)

    return fig_segment_dist, fig_rfm_segments, fig_segment_scores, fig_new_segment_dist

@app.route('/')
def index():
    data = preprocess_data()
    fig_segment_dist, fig_rfm_segments, fig_segment_scores, fig_new_segment_dist = create_plots(data)

    plot_segment_dist_html = fig_to_html(fig_segment_dist)
    plot_rfm_segments_html = fig_to_html(fig_rfm_segments)
    plot_segment_scores_html = fig_to_html(fig_segment_scores)
    plot_new_segment_dist_html = fig_to_html(fig_new_segment_dist)

    return render_template_string("""
        <!doctype html>
        <html>
        <head><title>RFM Analysis</title></head>
        <body>
            <h1>RFM Analysis Plots</h1>
            <div>
                <h2>RFM Value Segment Distribution</h2>
                {{ plot_segment_dist_html|safe }}
            </div>
            <div>
                <h2>Comparison of RFM Customer Segments</h2>
                {{ plot_rfm_segments_html|safe }}
            </div>
            <div>
                <h2>Comparison of RFM Segments based on Scores</h2>
                {{ plot_segment_scores_html|safe }}
            </div>
            <div>
                <h2>New Distribution of RFM Segments after Re-engagement</h2>
                {{ plot_new_segment_dist_html|safe }}
            </div>
        </body>
        </html>
        """, plot_segment_dist_html=plot_segment_dist_html,
           plot_rfm_segments_html=plot_rfm_segments_html,
           plot_segment_scores_html=plot_segment_scores_html,
           plot_new_segment_dist_html=plot_new_segment_dist_html)

if __name__ == '__main__':
    app.run(debug=True)
