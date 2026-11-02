import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import { Alert, Box, Card, CardActionArea, CardContent, Chip, Stack, Tooltip, Typography } from '@mui/material';
import { LEVEL_COLORS, LEVEL_LABELS, LEVEL_ORDER, ROUTE_COLORS, formatDuration } from '../format';
import type { Plan, Route } from '../types';

interface Props {
  plan: Plan;
  selectedId: string;
  onSelect: (id: string) => void;
}

/** Stacked bar: each segment's width is the miles spent at that risk level. */
function RiskBar({ route }: { route: Route }) {
  const m = route.summary.miles_by_level;
  return (
    <Box
      aria-label="Miles by risk level"
      sx={{ display: 'flex', height: 8, borderRadius: 1, overflow: 'hidden', bgcolor: 'divider' }}
    >
      {LEVEL_ORDER.map((lvl) =>
        m[lvl] > 0 ? (
          <Tooltip key={lvl} title={`${LEVEL_LABELS[lvl]}: ${m[lvl]} mi`}>
            <Box sx={{ flexGrow: m[lvl], bgcolor: LEVEL_COLORS[lvl] }} />
          </Tooltip>
        ) : null,
      )}
    </Box>
  );
}

export default function RouteList({ plan, selectedId, onSelect }: Props) {
  return (
    <Stack spacing={1.25} sx={{ mt: 2.5 }}>
      <Alert severity="success" icon={<CheckCircleIcon fontSize="inherit" />}>
        {plan.recommendation_reason}
      </Alert>

      {plan.routes.map((r) => {
        const m = r.summary.miles_by_level;
        const selected = r.id === selectedId;
        const risky = (['no_travel', 'severe', 'high'] as const).filter((l) => m[l] > 0);
        return (
          <Card
            key={r.id}
            sx={{
              borderLeft: 4,
              borderLeftColor: ROUTE_COLORS[r.id],
              outline: selected ? 2 : 0,
              outlineColor: 'primary.main',
              outlineOffset: -1,
            }}
          >
            <CardActionArea onClick={() => onSelect(r.id)} aria-pressed={selected}>
              <CardContent sx={{ py: 1.5, '&:last-child': { pb: 1.5 } }}>
                <Stack direction="row" justifyContent="space-between" alignItems="center">
                  <Typography fontWeight={700}>Route {r.id}</Typography>
                  {r.id === plan.recommended_id && <Chip label="Recommended" color="success" size="small" />}
                </Stack>
                {r.via && (
                  <Typography variant="body2" color="text.secondary" noWrap title={r.via}>
                    via {r.via}
                  </Typography>
                )}
                <Stack direction="row" spacing={1.5} sx={{ my: 1 }}>
                  <Typography variant="body2">{Math.round(r.distance_mi)} mi</Typography>
                  <Typography variant="body2">{formatDuration(r.duration_s)}</Typography>
                  <Typography variant="body2" color="text.secondary">
                    avg risk {r.summary.avg_risk.toFixed(2)}
                  </Typography>
                </Stack>
                <RiskBar route={r} />
                <Stack direction="row" spacing={1.25} sx={{ mt: 1 }}>
                  {risky.length === 0 ? (
                    <Typography variant="caption" color="text.secondary" fontWeight={600}>
                      No high-risk miles
                    </Typography>
                  ) : (
                    risky.map((lvl) => (
                      <Typography key={lvl} variant="caption" fontWeight={700} sx={{ color: LEVEL_COLORS[lvl] }}>
                        {m[lvl]} mi {LEVEL_LABELS[lvl]}
                      </Typography>
                    ))
                  )}
                </Stack>
              </CardContent>
            </CardActionArea>
          </Card>
        );
      })}
    </Stack>
  );
}
