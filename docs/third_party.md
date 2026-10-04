# Third-party components

Every external library, model, API, dataset and service used by Jachai, with its
licence (Rulebook HR 4.4, 9.2). Add a row **in the same commit** that introduces
the component.

| Name | Version | Licence | Purpose |
| --- | --- | --- | --- |
| setuptools | >=69 (build only) | MIT | Builds and installs the `jachai` and `jachai-backend` packages |
| pytest | 9.1.1 | MIT | Test runner |
| ruff | 0.16.10 | MIT | Linter and formatter |
| actions/checkout | v7 | MIT | GitHub Actions: check out the repo in CI |
| actions/setup-python | v7 | MIT | GitHub Actions: install Python 3.12 in CI |
| NumPy | 2.5.3 | BSD-3-Clause | Random number generation and array maths for the synthetic world |
| pandas | 3.0.6 | BSD-3-Clause | Tables for the synthetic world and features |
| PyArrow | 25.0.1 | Apache-2.0 | Parquet files for generated data |
| Pydantic | 2.13.5 | MIT | Validates configs/*.yaml when loaded |
| PyYAML | 6.0.3 | MIT | Reads configs/*.yaml |
| scikit-learn | 1.9.1 | BSD-3-Clause | Evaluation metrics (PR-AUC, ROC-AUC); models later |
| SciPy | 1.18.1 | BSD-3-Clause | Installed with scikit-learn |
| joblib | 1.6.0 | BSD-3-Clause | Saves the calibration model; installed with scikit-learn |
| threadpoolctl | 3.7.0 | BSD-3-Clause | Installed with scikit-learn |
| LightGBM | 4.7.0 | MIT | Payment risk model (gradient-boosted trees) |
| NetworkX | 3.7 | BSD-3-Clause | Payer-shop graph and Louvain communities for the network score |
| FastAPI | 0.142.2 | MIT | Backend API framework |
| Starlette | 1.7.0 | BSD-3-Clause | Installed with FastAPI (web toolkit, CORS middleware) |
| Uvicorn | 0.54.0 | BSD-3-Clause | Runs the API server |
| HTTPX | 0.28.1 | BSD-3-Clause | HTTP client used by FastAPI's test client (tests only) |
| Next.js | 16.3.8 | MIT | Dashboard framework (frontend/) |
| React / React DOM | 19.3.0 | MIT | Dashboard UI |
| TypeScript | 5.9.3 | Apache-2.0 | Dashboard type checking |
| Tailwind CSS (+ @tailwindcss/postcss) | 4.3.3 | MIT | Dashboard styling |
| PostCSS | 8.5.28 | MIT | CSS build step for Tailwind |
| Recharts | 3.10.1 | MIT | Dashboard charts (simulator, timeline) |
| @fontsource/noto-sans-bengali (Noto Sans Bengali font) | 5.3.0 | OFL-1.1 | Self-hosted Bangla font (works offline) |
| @types/react, @types/react-dom, @types/node | 19.3.0 / 19.3.0 / 26.6.4 | MIT | TypeScript type definitions |
