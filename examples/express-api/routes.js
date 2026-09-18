// Tiny Express-style API. Breakproof reads this, never runs it.
const express = require("express");

const app = express();
const router = express.Router();

function listUsers(req, res) { res.json([]); }
function createOrder(req, res) { res.status(201).json({}); }
function deleteOrder(req, res) { res.status(204).end(); }

app.get("/users", listUsers);
app.post("/orders", createOrder);
router.delete("/orders/:id", deleteOrder);

module.exports = { app, router };
