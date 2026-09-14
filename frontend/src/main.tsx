import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import { ToastProvider } from "./components/ui/Toast";
import App from "./App";
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/ui.css";
import "./styles/layout.css";
// 页面模块样式（自 pages.css 拆分，见 P3_设计升级_变更记录）
import "./styles/pages/auth.css";
import "./styles/pages/profile.css";
import "./styles/pages/onboarding.css";
import "./styles/pages/explore.css";
import "./styles/pages/target-job.css";
import "./styles/pages/prepare.css";
import "./styles/pages/tracking.css";
import "./styles/pages/offer.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <ToastProvider>
          <App />
        </ToastProvider>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>
);
