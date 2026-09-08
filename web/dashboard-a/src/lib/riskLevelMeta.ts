import type { RiskLevel } from '../types/risk'

export interface RiskLevelMetaEntry {
  label: string
  colorVar: string
  glowClass: string
  overlayDescription: string
}

const META: Record<RiskLevel, RiskLevelMetaEntry> = {
  low: { label: 'Low', colorVar: 'var(--risk-low)', glowClass: 'glow-low', overlayDescription: 'No overlay shown to the user.' },
  medium: {
    label: 'Medium',
    colorVar: 'var(--risk-medium)',
    glowClass: 'glow-medium',
    overlayDescription: 'Amber chip shown to the user.',
  },
  high: {
    label: 'High',
    colorVar: 'var(--risk-high)',
    glowClass: 'glow-high',
    overlayDescription: 'Red overlay shown to the user.',
  },
  critical: {
    label: 'Critical',
    colorVar: 'var(--risk-critical)',
    glowClass: 'glow-critical',
    overlayDescription: 'Red overlay plus an action prompt.',
  },
}

/**
 * The only function allowed to map a RiskLevel to a color, icon, or label.
 * Nothing else in this app may branch on risk_level or interpolate a color
 * from `score` directly: the app renders risk_level as sent, never
 * re-derives a band from the numeric score.
 */
export function riskLevelMeta(level: RiskLevel): RiskLevelMetaEntry {
  return META[level]
}
