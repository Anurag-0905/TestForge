import dash
from dash import html, dcc, Input, Output, State, callback_context
import dash_bootstrap_components as dbc
import plotly.graph_objs as go
import base64, io, pandas as pd
from scipy.stats import ttest_ind
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
import webbrowser, threading

server = Flask(__name__)
CORS(server)
experiments = []
experiment_id = 1

@server.route("/experiment", methods=["POST"])
def create_experiment():
    global experiment_id
    data = request.json
    name = data.get("name")
    variant_a = data.get("variant_a_data")
    variant_b = data.get("variant_b_data")
    if not name or not variant_a or not variant_b:
        return jsonify({"message": "Missing required fields"}), 400
    try:
        t_stat, p_value = ttest_ind(variant_a, variant_b)
    except Exception as e:
        return jsonify({"message": f"Error during t-test: {str(e)}"}), 500
    exp = {"id": experiment_id, "name": name, "variant_a": variant_a, "variant_b": variant_b, "p_value": p_value, "test_used": "t-test"}
    experiments.append(exp)
    experiment_id += 1
    return jsonify({"message": "Experiment created successfully!", "experiment": exp}), 200

@server.route("/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"message": "No file uploaded"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"message": "No file selected"}), 400
    try:
        df = pd.read_csv(file)
    except Exception as e:
        return jsonify({"message": f"Error reading CSV file: {str(e)}"}), 500
    if "variant_a" not in df.columns or "variant_b" not in df.columns:
        return jsonify({"message": "CSV must contain 'variant_a' and 'variant_b' columns"}), 400
    variant_a = df["variant_a"].dropna().tolist()
    variant_b = df["variant_b"].dropna().tolist()
    return jsonify({"message": "File processed successfully", "variant_a": variant_a, "variant_b": variant_b}), 200

@server.route("/experiments", methods=["GET"])
def get_experiments():
    return jsonify(experiments), 200

app = dash.Dash(__name__, server=server, external_stylesheets=[dbc.themes.LUX])
app.layout = dbc.Container([
    dbc.Row([dbc.Col(html.H1("Experiment Dashboard", className="text-center my-4"), width=12)]),
    dbc.Row([
        dbc.Col(
            dbc.Card([
                dbc.CardHeader("Run Experiment"),
                dbc.CardBody([
                    dbc.Input(id="exp-name", type="text", placeholder="Enter Experiment Name", className="mb-2"),
                    dbc.Textarea(id="variant-a", placeholder="Variant A Data (comma separated)", className="mb-2"),
                    dbc.Textarea(id="variant-b", placeholder="Variant B Data (comma separated)", className="mb-2"),
                    dbc.Button("Run Experiment", id="run-btn", color="success", className="w-100"),
                    html.Div(id="run-result", className="mt-2")
                ])
            ]), width=6
        ),
        dbc.Col(
            dbc.Card([
                dbc.CardHeader("Upload CSV"),
                dbc.CardBody([
                    dcc.Upload(
                        id="upload-data",
                        children=html.Div(["Drag and drop or click to select a file"]),
                        style={"width": "100%", "height": "60px", "lineHeight": "60px", "borderWidth": "1px", "borderStyle": "dashed", "borderRadius": "5px", "textAlign": "center", "margin": "10px 0"},
                        multiple=False
                    ),
                    dbc.Button("Upload File", id="upload-btn", color="primary", className="w-100"),
                    html.Div(id="upload-result", className="mt-2")
                ])
            ]), width=6
        )
    ]),
    dbc.Row([
        dbc.Col(
            dbc.Card([
                dbc.CardHeader("Experiments"),
                dbc.CardBody([
                    dbc.Button("Refresh Experiments", id="refresh-btn", color="info", className="w-100 mb-2"),
                    html.Div(id="exp-list"),
                    dcc.Graph(id="exp-graph")
                ])
            ]), width=12
        )
    ])
], fluid=True)

@app.callback(
    Output("run-result", "children"),
    Input("run-btn", "n_clicks"),
    State("exp-name", "value"),
    State("variant-a", "value"),
    State("variant-b", "value")
)
def run_experiment(n_clicks, name, variant_a, variant_b):
    if not n_clicks:
        return ""
    if not name or not variant_a or not variant_b:
        return dbc.Alert("Please provide experiment name and both variant data", color="warning")
    try:
        headers = {"Content-Type": "application/json"}
        payload = {"name": name, "variant_a_data": [float(x.strip()) for x in variant_a.split(",") if x.strip()], "variant_b_data": [float(x.strip()) for x in variant_b.split(",") if x.strip()]}
        response = requests.post("http://localhost:8050/experiment", json=payload, headers=headers)
        if response.status_code == 200:
            return dbc.Alert("Experiment created successfully!", color="success")
        else:
            message = response.json().get("message", "Unknown error")
            return dbc.Alert("Error: " + message, color="danger")
    except Exception as e:
        return dbc.Alert("Error: " + str(e), color="danger")

@app.callback(
    Output("upload-result", "children"),
    Input("upload-data", "contents"),
    State("upload-data", "filename")
)
def upload_file(contents, filename):
    if not contents:
        return ""
    content_type, content_string = contents.split(",")
    decoded = base64.b64decode(content_string)
    try:
        files = {"file": (filename, io.BytesIO(decoded), "text/csv")}
        response = requests.post("http://localhost:8050/upload", files=files)
        if response.status_code == 200:
            return dbc.Alert("File uploaded and processed successfully", color="success")
        else:
            message = response.json().get("message", "Error processing file")
            return dbc.Alert("Error: " + message, color="danger")
    except Exception as e:
        return dbc.Alert("Error: " + str(e), color="danger")

@app.callback(
    [Output("exp-list", "children"), Output("exp-graph", "figure")],
    Input("refresh-btn", "n_clicks")
)
def refresh_experiments(n_clicks):
    if not n_clicks:
        return "", {"data": []}
    try:
        response = requests.get("http://localhost:8050/experiments")
        if response.status_code != 200:
            return dbc.Alert("Error fetching experiments", color="danger"), {"data": []}
        exps = response.json()
        list_items = []
        ids = []
        pvals = []
        for exp in exps:
            list_items.append(html.P(f"ID: {exp['id']}, Name: {exp['name']}, p-value: {exp['p_value']:.4f}, Test: {exp['test_used']}"))
            if exp.get("p_value") is not None:
                ids.append(exp["id"])
                pvals.append(exp["p_value"])
        fig = go.Figure(data=[go.Bar(x=ids, y=pvals)]) if ids else {"data": []}
        if ids:
            fig.update_layout(title="Experiment p-values", xaxis_title="Experiment ID", yaxis_title="p-value")
        return list_items, fig
    except Exception as e:
        return dbc.Alert("Error: " + str(e), color="danger"), {"data": []}

if __name__ == "__main__":
    threading.Timer(1, lambda: webbrowser.open_new("http://localhost:8050")).start()
    app.run_server(debug=True, port=8050)
