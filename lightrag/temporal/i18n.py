"""
Internationalization (i18n) support for temporal operations.

This module provides Phase 4 (LOW priority) fix for:
- Issue #12: No Internationalization

Supports multiple languages for error messages, warnings, and user-facing text.

Usage:
    from lightrag.temporal.i18n import get_message, set_language

    # Set language
    set_language("es")  # Spanish

    # Get translated message
    msg = get_message("error.invalid_date", date="2024-02-30")
"""

import os
from typing import Any, Dict

# Default language
DEFAULT_LANGUAGE = os.getenv("LIGHTRAG_LANGUAGE", "en")

# Current language
_current_language = DEFAULT_LANGUAGE


# Message catalog
MESSAGES: Dict[str, Dict[str, str]] = {
    # English
    "en": {
        # Errors
        "error.invalid_date": "Invalid date: {date}",
        "error.invalid_date_format": "Invalid date format: '{date}'. Expected formats: {formats}",
        "error.date_out_of_range": "Date {date} is out of valid range ({min_year}-{max_year})",
        "error.not_leap_year": "{year} is not a leap year",
        "error.invalid_version": "Invalid version format: {version}",
        "error.version_out_of_range": "Version {version} is out of range (1-{max_version})",
        "error.empty_entity_name": "Entity name cannot be empty",
        "error.transaction_failed": "Transaction failed and rolled back: {error}",
        "error.lock_timeout": "Failed to acquire lock after {timeout} seconds",
        "error.sequence_allocation_failed": "Failed to allocate sequence index: {error}",
        # Warnings
        "warning.deprecated_parameter": "Parameter '{param}' is deprecated and will be removed in v{version}. {suggestion}",
        "warning.future_date": "Date {date} is in the future",
        "warning.empty_results": "No results found for {operation}",
        "warning.filtered_entities": "Filtered out {count} invalid entities",
        "warning.version_limit_reached": "Version limit ({limit}) reached for entity: {entity}",
        # Info
        "info.sequence_allocated": "Allocated sequence index: {index}",
        "info.transaction_committed": "Transaction committed successfully",
        "info.temporal_filter_applied": "Applied temporal filter: {mode}",
        "info.entities_filtered": "Filtered {input_count} → {output_count} entities",
        # Success
        "success.insert_complete": "Successfully inserted {count} documents",
        "success.delete_complete": "Successfully deleted entity: {entity}",
        "success.update_complete": "Successfully updated entity: {entity}",
    },
    # Spanish
    "es": {
        # Errors
        "error.invalid_date": "Fecha inválida: {date}",
        "error.invalid_date_format": "Formato de fecha inválido: '{date}'. Formatos esperados: {formats}",
        "error.date_out_of_range": "La fecha {date} está fuera del rango válido ({min_year}-{max_year})",
        "error.not_leap_year": "{year} no es un año bisiesto",
        "error.invalid_version": "Formato de versión inválido: {version}",
        "error.version_out_of_range": "La versión {version} está fuera de rango (1-{max_version})",
        "error.empty_entity_name": "El nombre de la entidad no puede estar vacío",
        "error.transaction_failed": "La transacción falló y se revirtió: {error}",
        "error.lock_timeout": "No se pudo adquirir el bloqueo después de {timeout} segundos",
        "error.sequence_allocation_failed": "Error al asignar índice de secuencia: {error}",
        # Warnings
        "warning.deprecated_parameter": "El parámetro '{param}' está obsoleto y se eliminará en v{version}. {suggestion}",
        "warning.future_date": "La fecha {date} está en el futuro",
        "warning.empty_results": "No se encontraron resultados para {operation}",
        "warning.filtered_entities": "Se filtraron {count} entidades inválidas",
        "warning.version_limit_reached": "Se alcanzó el límite de versión ({limit}) para la entidad: {entity}",
        # Info
        "info.sequence_allocated": "Índice de secuencia asignado: {index}",
        "info.transaction_committed": "Transacción confirmada exitosamente",
        "info.temporal_filter_applied": "Filtro temporal aplicado: {mode}",
        "info.entities_filtered": "Entidades filtradas {input_count} → {output_count}",
        # Success
        "success.insert_complete": "Se insertaron exitosamente {count} documentos",
        "success.delete_complete": "Entidad eliminada exitosamente: {entity}",
        "success.update_complete": "Entidad actualizada exitosamente: {entity}",
    },
    # French
    "fr": {
        # Errors
        "error.invalid_date": "Date invalide: {date}",
        "error.invalid_date_format": "Format de date invalide: '{date}'. Formats attendus: {formats}",
        "error.date_out_of_range": "La date {date} est hors de la plage valide ({min_year}-{max_year})",
        "error.not_leap_year": "{year} n'est pas une année bissextile",
        "error.invalid_version": "Format de version invalide: {version}",
        "error.version_out_of_range": "La version {version} est hors de portée (1-{max_version})",
        "error.empty_entity_name": "Le nom de l'entité ne peut pas être vide",
        "error.transaction_failed": "La transaction a échoué et a été annulée: {error}",
        "error.lock_timeout": "Impossible d'acquérir le verrou après {timeout} secondes",
        "error.sequence_allocation_failed": "Échec de l'allocation de l'index de séquence: {error}",
        # Warnings
        "warning.deprecated_parameter": "Le paramètre '{param}' est obsolète et sera supprimé dans v{version}. {suggestion}",
        "warning.future_date": "La date {date} est dans le futur",
        "warning.empty_results": "Aucun résultat trouvé pour {operation}",
        "warning.filtered_entities": "{count} entités invalides filtrées",
        "warning.version_limit_reached": "Limite de version ({limit}) atteinte pour l'entité: {entity}",
        # Info
        "info.sequence_allocated": "Index de séquence alloué: {index}",
        "info.transaction_committed": "Transaction validée avec succès",
        "info.temporal_filter_applied": "Filtre temporel appliqué: {mode}",
        "info.entities_filtered": "Entités filtrées {input_count} → {output_count}",
        # Success
        "success.insert_complete": "{count} documents insérés avec succès",
        "success.delete_complete": "Entité supprimée avec succès: {entity}",
        "success.update_complete": "Entité mise à jour avec succès: {entity}",
    },
    # German
    "de": {
        # Errors
        "error.invalid_date": "Ungültiges Datum: {date}",
        "error.invalid_date_format": "Ungültiges Datumsformat: '{date}'. Erwartete Formate: {formats}",
        "error.date_out_of_range": "Datum {date} liegt außerhalb des gültigen Bereichs ({min_year}-{max_year})",
        "error.not_leap_year": "{year} ist kein Schaltjahr",
        "error.invalid_version": "Ungültiges Versionsformat: {version}",
        "error.version_out_of_range": "Version {version} liegt außerhalb des Bereichs (1-{max_version})",
        "error.empty_entity_name": "Entitätsname darf nicht leer sein",
        "error.transaction_failed": "Transaktion fehlgeschlagen und zurückgesetzt: {error}",
        "error.lock_timeout": "Sperre konnte nach {timeout} Sekunden nicht erworben werden",
        "error.sequence_allocation_failed": "Sequenzindex-Zuweisung fehlgeschlagen: {error}",
        # Warnings
        "warning.deprecated_parameter": "Parameter '{param}' ist veraltet und wird in v{version} entfernt. {suggestion}",
        "warning.future_date": "Datum {date} liegt in der Zukunft",
        "warning.empty_results": "Keine Ergebnisse für {operation} gefunden",
        "warning.filtered_entities": "{count} ungültige Entitäten herausgefiltert",
        "warning.version_limit_reached": "Versionslimit ({limit}) für Entität erreicht: {entity}",
        # Info
        "info.sequence_allocated": "Sequenzindex zugewiesen: {index}",
        "info.transaction_committed": "Transaktion erfolgreich bestätigt",
        "info.temporal_filter_applied": "Temporaler Filter angewendet: {mode}",
        "info.entities_filtered": "Entitäten gefiltert {input_count} → {output_count}",
        # Success
        "success.insert_complete": "{count} Dokumente erfolgreich eingefügt",
        "success.delete_complete": "Entität erfolgreich gelöscht: {entity}",
        "success.update_complete": "Entität erfolgreich aktualisiert: {entity}",
    },
    # Chinese (Simplified)
    "zh": {
        # Errors
        "error.invalid_date": "无效日期: {date}",
        "error.invalid_date_format": "无效的日期格式: '{date}'. 期望格式: {formats}",
        "error.date_out_of_range": "日期 {date} 超出有效范围 ({min_year}-{max_year})",
        "error.not_leap_year": "{year} 不是闰年",
        "error.invalid_version": "无效的版本格式: {version}",
        "error.version_out_of_range": "版本 {version} 超出范围 (1-{max_version})",
        "error.empty_entity_name": "实体名称不能为空",
        "error.transaction_failed": "事务失败并已回滚: {error}",
        "error.lock_timeout": "在 {timeout} 秒后无法获取锁",
        "error.sequence_allocation_failed": "序列索引分配失败: {error}",
        # Warnings
        "warning.deprecated_parameter": "参数 '{param}' 已弃用，将在 v{version} 中删除。{suggestion}",
        "warning.future_date": "日期 {date} 在未来",
        "warning.empty_results": "未找到 {operation} 的结果",
        "warning.filtered_entities": "过滤掉 {count} 个无效实体",
        "warning.version_limit_reached": "实体 {entity} 达到版本限制 ({limit})",
        # Info
        "info.sequence_allocated": "已分配序列索引: {index}",
        "info.transaction_committed": "事务成功提交",
        "info.temporal_filter_applied": "已应用时间过滤器: {mode}",
        "info.entities_filtered": "实体过滤 {input_count} → {output_count}",
        # Success
        "success.insert_complete": "成功插入 {count} 个文档",
        "success.delete_complete": "成功删除实体: {entity}",
        "success.update_complete": "成功更新实体: {entity}",
    },
}


def set_language(language: str) -> bool:
    """
    Set the current language for messages.

    Args:
        language: Language code (e.g., "en", "es", "fr", "de", "zh")

    Returns:
        True if language is supported, False otherwise

    Examples:
        >>> set_language("es")
        True
        >>> set_language("invalid")
        False
    """
    global _current_language

    if language in MESSAGES:
        _current_language = language
        return True
    else:
        # Fallback to English
        _current_language = "en"
        return False


def get_language() -> str:
    """Get the current language code."""
    return _current_language


def get_message(key: str, **kwargs: Any) -> str:
    """
    Get a translated message with parameter substitution.

    Args:
        key: Message key (e.g., "error.invalid_date")
        **kwargs: Parameters to substitute in the message

    Returns:
        Translated and formatted message

    Examples:
        >>> get_message("error.invalid_date", date="2024-02-30")
        "Invalid date: 2024-02-30"

        >>> set_language("es")
        >>> get_message("error.invalid_date", date="2024-02-30")
        "Fecha inválida: 2024-02-30"
    """
    # Get message catalog for current language
    catalog = MESSAGES.get(_current_language, MESSAGES["en"])

    # Get message template
    template = catalog.get(key)

    if template is None:
        # Fallback to English
        template = MESSAGES["en"].get(key, f"[Missing message: {key}]")

    # Format with parameters
    try:
        return template.format(**kwargs)
    except KeyError as e:
        return f"{template} [Missing parameter: {e}]"


def get_supported_languages() -> list[str]:
    """
    Get list of supported language codes.

    Returns:
        List of language codes

    Examples:
        >>> get_supported_languages()
        ['en', 'es', 'fr', 'de', 'zh']
    """
    return list(MESSAGES.keys())


def add_language(language: str, messages: Dict[str, str]) -> None:
    """
    Add a new language or update existing language messages.

    Args:
        language: Language code
        messages: Dictionary of message key -> translated text

    Examples:
        >>> add_language("ja", {
        ...     "error.invalid_date": "無効な日付: {date}"
        ... })
    """
    if language in MESSAGES:
        # Update existing
        MESSAGES[language].update(messages)
    else:
        # Add new
        MESSAGES[language] = messages


class I18nError(Exception):
    """
    Internationalized error with automatic translation.

    Usage:
        raise I18nError("error.invalid_date", date="2024-02-30")
    """

    def __init__(self, message_key: str, **kwargs: Any):
        self.message_key = message_key
        self.params = kwargs
        self.message = get_message(message_key, **kwargs)
        super().__init__(self.message)


class I18nWarning(UserWarning):
    """
    Internationalized warning with automatic translation.

    Usage:
        warnings.warn(I18nWarning("warning.future_date", date="2025-01-01"))
    """

    def __init__(self, message_key: str, **kwargs: Any):
        self.message_key = message_key
        self.params = kwargs
        self.message = get_message(message_key, **kwargs)
        super().__init__(self.message)


#
