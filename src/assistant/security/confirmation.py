def terminal_confirm(description: str) -> bool:
    return input(f"Confirmar / Confirm {description}? [sim/yes]: ").strip().lower() in {
        "sim",
        "yes",
    }
