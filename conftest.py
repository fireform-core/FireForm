def pytest_addoption(parser):
    parser.addoption(
        "--verbose-eval",
        action="store_true",
        default=False,
        help="Show detailed value-by-value comparison lines during benchmark evaluation",
    )
