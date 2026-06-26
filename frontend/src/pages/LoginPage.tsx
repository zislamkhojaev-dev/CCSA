import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";

export default function LoginPage() {
  const navigate = useNavigate();
  const [login, setLogin] = useState("admin");
  const [password, setPassword] = useState("admin123");
  const [error, setError] = useState("");

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      await api.post("/auth/login", { login, password });
      navigate("/");
    } catch {
      setError("Неверный логин или пароль");
    }
  };

  return (
    <div className="login-page">
      <div className="card login-card">
        <h1 className="page-title">CCSA — Вход</h1>
        <form onSubmit={submit}>
          <div className="form-group">
            <label>Логин</label>
            <input value={login} onChange={(e) => setLogin(e.target.value)} required />
          </div>
          <div className="form-group">
            <label>Пароль</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </div>
          {error && <p style={{ color: "var(--red)", marginBottom: "1rem" }}>{error}</p>}
          <button type="submit" className="btn btn-primary" style={{ width: "100%" }}>
            Войти
          </button>
        </form>
      </div>
    </div>
  );
}
