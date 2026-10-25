"""Strings translated through variables, for tools/i18n_check.py."""


def dynamic_keys():
    import morph
    keys = list(morph.QUALITIES)
    for _args, descs in morph.AUDIO_SPEC.values():
        keys += descs
    return keys
