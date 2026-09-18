"""Tiny Flask-style API. Breakproof reads this, never runs it."""
from flask import Flask

app = Flask(__name__)


@app.get("/users")
def list_users():
    return []


@app.post("/orders")
def create_order():
    return {}, 201


@app.delete("/orders/<order_id>")
def delete_order(order_id):
    return {}, 204
