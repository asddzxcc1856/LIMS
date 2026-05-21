/**
 * useLocalizedLabel — pick the right column for the current locale.
 *
 * Catalog rows (Experiment, EquipmentType, Recipe …) carry both the
 * primary zh-TW string and an optional ``*_en`` column. We hide the
 * column-picking logic behind a single helper so every consuming
 * component reads ``localizedName(row)`` instead of branching on
 * ``locale.value`` itself.
 */
import { useI18n } from 'vue-i18n'

export function useLocalizedLabel() {
  const { locale } = useI18n()

  /**
   * Resolve the display string for ``row`` using the ``baseKey`` column
   * (defaults to ``name``). When the locale is English we prefer the
   * ``<baseKey>_en`` variant if it's non-empty; otherwise we fall back
   * to the base column so nothing renders as blank.
   */
  function localized(row, baseKey = 'name') {
    if (!row) return ''
    const en = row[`${baseKey}_en`]
    const zh = row[baseKey]
    if (locale.value === 'en') return en || zh || ''
    return zh || en || ''
  }

  return { localized }
}
