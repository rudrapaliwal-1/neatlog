import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import OperatorSession from "./components/OperatorSession";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode><BrowserRouter><OperatorSession><App /></OperatorSession></BrowserRouter></React.StrictMode>,
);
