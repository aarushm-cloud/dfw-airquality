import type { AqiCategory } from './aqi';

export type CategoryGuidance = {
  whoTakeCare: string[];
  activity: string[];
};

export const HEALTH_GUIDANCE: Record<AqiCategory, CategoryGuidance> = {
  good: {
    whoTakeCare: [
      'No groups affected at this level',
      'Air quality poses little or no health risk',
    ],
    activity: [
      'Great day to be active outside',
      'All outdoor activities are OK',
    ],
  },
  moderate: {
    whoTakeCare: [
      'People unusually sensitive to particle pollution',
      'Watch for coughing or shortness of breath if sensitive',
    ],
    activity: [
      'Most people: a good day to be active outside',
      'Sensitive individuals: consider shorter or less intense outdoor activities',
    ],
  },
  sensitive: {
    whoTakeCare: [
      'People with heart or lung disease',
      'Older adults, children, and teenagers',
      'Pregnant people and outdoor workers',
    ],
    activity: [
      'Sensitive groups: shorter, less intense outdoor activities; take more breaks',
      'People with asthma: keep quick-relief medication on hand',
      'Most others: outdoor activity is OK with normal precautions',
    ],
  },
  unhealthy: {
    whoTakeCare: [
      'Everyone may begin to experience health effects',
      'Sensitive groups may experience more serious effects',
    ],
    activity: [
      'Sensitive groups: avoid long or intense outdoor activity; move indoors when possible',
      'Everyone else: reduce long or intense outdoor activity; take more breaks',
    ],
  },
  veryUnhealthy: {
    whoTakeCare: [
      'Everyone is at increased risk',
      'Health alert: serious effects possible for sensitive groups',
    ],
    activity: [
      'Sensitive groups: avoid all physical activity outdoors',
      'Everyone else: avoid long or intense outdoor activity; reschedule or move indoors',
      'Close windows; run HVAC with HEPA filtration if available',
    ],
  },
  hazardous: {
    whoTakeCare: [
      'Everyone is affected — emergency conditions',
      'Sensitive groups: serious health effects likely',
    ],
    activity: [
      'Everyone: avoid all outdoor physical activity',
      'Stay indoors; keep activity levels low',
      'Run HEPA air cleaner; close windows; check on neighbors in sensitive groups',
    ],
  },
};

export const GUIDANCE_SOURCE_URL = 'https://document.airnow.gov/air-quality-guide-for-particle-pollution.pdf';
export const GUIDANCE_SOURCE_LABEL = 'EPA AirNow Air Quality Guide';
