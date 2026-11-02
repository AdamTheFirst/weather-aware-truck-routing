import { createTheme } from '@mui/material/styles';

// One theme for the whole app: colours, radius, type scale and a few
// component defaults, so screens don't each invent their own spacing.
export const theme = createTheme({
  palette: {
    primary: { main: '#2563eb' },
    success: { main: '#2e9e5b' },
    background: { default: '#f6f7f9', paper: '#ffffff' },
    text: { primary: '#16181d', secondary: '#6b7280' },
    divider: '#e5e7eb',
  },
  shape: { borderRadius: 10 },
  typography: {
    fontFamily: 'Inter, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
    h1: { fontSize: '1.15rem', fontWeight: 700 },
    button: { textTransform: 'none', fontWeight: 600 },
    overline: { fontWeight: 600, letterSpacing: '0.04em', lineHeight: 1.6 },
  },
  components: {
    MuiTextField: { defaultProps: { size: 'small', fullWidth: true } },
    MuiButton: { defaultProps: { disableElevation: true } },
    MuiPaper: { defaultProps: { elevation: 0 } },
    MuiCard: { defaultProps: { variant: 'outlined' } },
  },
});
