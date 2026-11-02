import PauseIcon from '@mui/icons-material/Pause';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import { Box, FormControlLabel, IconButton, Paper, Slider, Stack, Switch, Typography } from '@mui/material';
import { useEffect, useState } from 'react';
import { LEVEL_COLORS, LEVEL_LABELS, LEVEL_ORDER, formatTime } from '../format';

interface Props {
  departure: string;
  hour: number;
  max: number;
  onChange: (h: number) => void;
  showHeatmap: boolean;
  onToggleHeatmap: (v: boolean) => void;
}

/** 0–48 h forecast slider with a play button and the risk legend. */
export default function HourSlider({ departure, hour, max, onChange, showHeatmap, onToggleHeatmap }: Props) {
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    if (!playing) return;
    const id = window.setInterval(() => onChange(hour >= max ? 0 : hour + 1), 400);
    return () => window.clearInterval(id);
  }, [playing, hour, max, onChange]);

  const at = new Date(new Date(departure).getTime() + hour * 3600_000).toISOString();

  return (
    <Paper
      elevation={4}
      sx={{
        position: 'absolute',
        left: 16,
        right: 16,
        bottom: 24,
        zIndex: 1000,
        maxWidth: 720,
        mx: 'auto',
        px: 2,
        py: 1.25,
      }}
    >
      <Stack direction="row" alignItems="center" spacing={2}>
        <IconButton
          color="primary"
          onClick={() => setPlaying((p) => !p)}
          aria-label={playing ? 'Pause forecast' : 'Play forecast'}
          sx={{ bgcolor: 'primary.main', color: '#fff', '&:hover': { bgcolor: 'primary.dark' } }}
          size="small"
        >
          {playing ? <PauseIcon /> : <PlayArrowIcon />}
        </IconButton>
        <Slider
          value={hour}
          min={0}
          max={max}
          step={1}
          marks={[0, 12, 24, 36, 48].map((v) => ({ value: v }))}
          onChange={(_, v) => {
            setPlaying(false);
            onChange(v as number);
          }}
          valueLabelDisplay="auto"
          valueLabelFormat={(v) => `+${v} h`}
          aria-label="Forecast hour"
        />
        <Box sx={{ minWidth: 148, textAlign: 'right', flexShrink: 0 }}>
          <Typography variant="body2" fontWeight={700}>
            +{hour} h
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {formatTime(at)}
          </Typography>
        </Box>
      </Stack>

      <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" useFlexGap spacing={1}>
        <FormControlLabel
          control={<Switch size="small" checked={showHeatmap} onChange={(e) => onToggleHeatmap(e.target.checked)} />}
          label={<Typography variant="caption">Heatmap</Typography>}
        />
        <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap>
          {LEVEL_ORDER.map((l) => (
            <Stack key={l} direction="row" alignItems="center" spacing={0.5}>
              <Box sx={{ width: 10, height: 10, borderRadius: 0.5, bgcolor: LEVEL_COLORS[l] }} />
              <Typography variant="caption">{LEVEL_LABELS[l]}</Typography>
            </Stack>
          ))}
        </Stack>
      </Stack>
    </Paper>
  );
}
