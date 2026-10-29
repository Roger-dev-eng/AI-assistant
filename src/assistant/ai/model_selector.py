from dataclasses import replace


def select_model(settings, secondary=False):
    if not secondary:
        return settings
    if not settings.secondary_model_id:
        raise ValueError("Configure um modelo alternativo e suas tarifas antes de selecioná-lo.")
    return replace(
        settings,
        model_id=settings.secondary_model_id,
        input_rate=settings.secondary_input_rate,
        output_rate=settings.secondary_output_rate,
    )
