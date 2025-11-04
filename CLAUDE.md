# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## High-Level Code Architecture

The project is a Python-based AstrBot plugin for paper trading. It follows a modular architecture:

- **`main.py`**: The plugin's entry point, defining the `PaperTradingPlugin` class. It handles initialization of services, command handlers, and perennial tasks like order monitoring and daily maintenance.
- **`handlers/`**: Contains command handlers (`TradingCommandHandlers`, `QueryCommandHandlers`, `UserCommandHandlers`) that process user commands received from AstrBot. They interact with the services layer to fulfill requests.
- **`services/`**: Implements the core business logic. Key services include:
    - `TradeCoordinator`: orchestrates trading operations.
    - `UserInteractionService`: manages user interaction flows.
    - `StockDataService`: handles fetching and managing stock data.
    - `TradingEngine`: executes trading logic.
    - `OrderMonitorService`: monitors pending orders and executes them when conditions are met.
    - `MarketRulesEngine`: enforces trading rules (T+1, daily limits).
- **`utils/`**: Provides utility functions, primarily `DataStorage` for data persistence.
- **`models/`**: Likely contains data models for stocks, orders, users, etc. (Further exploration needed to confirm exact contents).
- **`_conf_schema.json`**: Defines the configuration schema for the plugin.

## Development Commands

This project is a Python application. Standard Python development practices apply.

- **Install dependencies**: `pip install -r requirements.txt`
- **Run the bot**: This plugin runs within the AstrBot framework. To run it, you would typically start AstrBot, ensuring this plugin is correctly placed in the `AstrBot/data/plugins/` directory as described in `README.md`.
- **Testing**: Not explicitly defined in `README.md`. It's recommended to establish a testing methodology, potentially using `pytest`.

## Important Notes

- The plugin uses Chinese for command names and documentation within the code.
- Asynchronous programming with `asyncio` is used extensively, especially for long-running tasks like order monitoring and daily maintenance.
- Configuration is managed through `_conf_schema.json` and accessed via `plugin_config`.