# Import required libraries
import dash
from dash import dcc, html, Input, Output, callback
import plotly.express as px
import pandas as pd
import numpy as np
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
import os
from waitress import serve  # For production server

# Load and preprocess the data
try:
    # Try to load from URL first, then local file
    url = "https://raw.githubusercontent.com/krishnaik06/Netflix-Data-Analysis/main/netflix_titles.csv"
    df = pd.read_csv(url, encoding='utf-8')
except:
    try:
        df = pd.read_csv('netflix_titles.csv', encoding='utf-8')
    except UnicodeDecodeError:
        df = pd.read_csv('netflix_titles.csv', encoding='latin1')
    except FileNotFoundError:
        raise Exception("Could not load Netflix data - neither from URL nor local file")

# Data cleaning and preprocessing
df['date_added'] = pd.to_datetime(df['date_added'], errors='coerce')
df['year_added'] = df['date_added'].dt.year

# Handle missing values
df['country'] = df['country'].fillna('Unknown')
df['rating'] = df['rating'].fillna('Unknown')

# Process duration
df['duration_num'] = df['duration'].str.extract(r'(\d+)').astype(float)
df['duration_unit'] = np.where(
    df['duration'].str.contains('min', na=False), 'min',
    np.where(df['duration'].str.contains('Season', na=False), 'season', None)
)

# Create separate columns for movie duration and TV show seasons
df['movie_duration'] = np.where(df['type'] == 'Movie', df['duration_num'], np.nan)
df['tv_seasons'] = np.where(df['type'] == 'TV Show', df['duration_num'], np.nan)

# Explode genres
df['genres'] = df['listed_in'].str.split(', ')
df = df.explode('genres')

# Create a clean release year column
df['release_year'] = pd.to_numeric(df['release_year'], errors='coerce')

# Initialize the Dash app
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
server = app.server  # Expose the server variable

# Define the layout of the dashboard
app.layout = dbc.Container([
    dbc.Row([
        dbc.Col(html.H1("Netflix Content Analysis Dashboard", className="text-center my-4"), width=12)
    ]),

    dbc.Row([
        # Sidebar with filters
        dbc.Col([
            html.H3("Filters", className="mb-3"),
            html.Hr(),

            html.H5("Release Year"),
            dcc.RangeSlider(
                id='year-slider',
                min=df['release_year'].min(),
                max=df['release_year'].max(),
                step=1,
                value=[df['release_year'].min(), df['release_year'].max()],
                marks={int(year): str(year) for year in 
                       range(int(df['release_year'].min()), int(df['release_year'].max()) + 1, 5)},
                tooltip={"placement": "bottom", "always_visible": True}
            ),

            html.H5("Content Type", className="mt-4"),
            dcc.Dropdown(
                id='type-dropdown',
                options=[{'label': 'All', 'value': 'All'},
                         {'label': 'Movies', 'value': 'Movie'},
                         {'label': 'TV Shows', 'value': 'TV Show'}],
                value='All',
                clearable=False
            ),

            html.H5("Country (Top 10)", className="mt-4"),
            dcc.Dropdown(
                id='country-dropdown',
                options=[{'label': 'All', 'value': 'All'}] +
                        [{'label': country, 'value': country}
                         for country in df['country'].value_counts().head(10).index],
                value='All',
                clearable=False
            )
        ], md=3, style={'background-color': '#f8f9fa', 'padding': '20px'}),

        # Main content area
        dbc.Col([
            dbc.Row([
                dbc.Col(dcc.Graph(id='type-pie-chart'), md=6),
                dbc.Col(dcc.Graph(id='genre-bar-chart'), md=6)
            ]),

            dbc.Row([
                dbc.Col(dcc.Graph(id='timeline-chart'), md=12)
            ], className="mt-4"),

            dbc.Row([
                dbc.Col(dcc.Graph(id='duration-scatter'), md=6),
                dbc.Col(dcc.Graph(id='country-map'), md=6)
            ], className="mt-4")
        ], md=9)
    ])
], fluid=True)

# Callback for updating all visualizations based on filters
@app.callback(
    [Output('type-pie-chart', 'figure'),
     Output('genre-bar-chart', 'figure'),
     Output('timeline-chart', 'figure'),
     Output('duration-scatter', 'figure'),
     Output('country-map', 'figure')],
    [Input('year-slider', 'value'),
     Input('type-dropdown', 'value'),
     Input('country-dropdown', 'value')]
)
def update_dashboard(selected_years, selected_type, selected_country):
    # Filter the dataframe based on user selections
    filtered_df = df[
        (df['release_year'] >= selected_years[0]) &
        (df['release_year'] <= selected_years[1])
    ]

    if selected_type != 'All':
        filtered_df = filtered_df[filtered_df['type'] == selected_type]

    if selected_country != 'All':
        filtered_df = filtered_df[filtered_df['country'].str.contains(selected_country, na=False)]

    # 1. Type Pie Chart
    type_counts = filtered_df['type'].value_counts().reset_index()
    type_counts.columns = ['type', 'count']
    type_pie = px.pie(
        type_counts,
        names='type',
        values='count',
        title='Movies vs. TV Shows',
        hole=0.3,
        color='type',
        color_discrete_map={'Movie': 'blue', 'TV Show': 'green'}
    )
    type_pie.update_traces(textposition='inside', textinfo='percent+label')

    # 2. Genre Bar Chart (Top 10)
    genre_counts = filtered_df['genres'].value_counts().head(10).reset_index()
    genre_counts.columns = ['genre', 'count']
    genre_bar = px.bar(
        genre_counts,
        x='count',
        y='genre',
        orientation='h',
        title='Top 10 Genres',
        color='genre'
    )
    genre_bar.update_layout(yaxis={'categoryorder': 'total ascending'})

    # 3. Release Timeline Chart
    timeline_df = filtered_df.groupby(['year_added', 'type']).size().reset_index(name='count')
    timeline = px.line(
        timeline_df,
        x='year_added',
        y='count',
        color='type',
        title='Content Added to Netflix Over Time',
        labels={'year_added': 'Year', 'count': 'Number of Titles'}
    )
    timeline.update_layout(hovermode='x unified')

    # 4. Duration Scatter Plot
    scatter_df = filtered_df.dropna(subset=['duration_num'])
    duration_scatter = px.scatter(
        scatter_df,
        x='release_year',
        y='duration_num',
        color='type',
        title='Content Duration Trends',
        labels={'release_year': 'Release Year', 'duration_num': 'Duration'},
        hover_data=['title'],
        facet_col='type',
        category_orders={'type': ['Movie', 'TV Show']}
    )
    duration_scatter.update_traces(marker=dict(size=8, opacity=0.6))
    duration_scatter.update_yaxes(matches=None)
    duration_scatter.for_each_yaxis(lambda yaxis: yaxis.update(title=''))
    duration_scatter.update_layout(yaxis1={'title': 'Minutes'}, yaxis2={'title': 'Seasons'})

    # 5. Country Choropleth Map
    exploded_countries = filtered_df.assign(
        country=filtered_df['country'].str.split(', ')
    ).explode('country')
    country_counts = exploded_countries['country'].value_counts().reset_index()
    country_counts.columns = ['country', 'count']
    
    country_map = px.choropleth(
        country_counts,
        locations='country',
        locationmode='country names',
        color='count',
        title='Content Production by Country',
        hover_name='country',
        color_continuous_scale=px.colors.sequential.Plasma
    )
    country_map.update_layout(geo=dict(showframe=False, showcoastlines=False))

    return type_pie, genre_bar, timeline, duration_scatter, country_map

# Run the app
if __name__ == '__main__':
    # For production use Waitress
    serve(server, host='0.0.0.0', port=8050)
