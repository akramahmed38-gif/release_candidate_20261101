import { createTheme } from '@mui/material/styles';

export const theme = createTheme({
  palette: {
    primary: {
      main: '#0b4fa8',
      dark: '#083a7a',
      light: '#1f63be',
      contrastText: '#ffffff',
    },
    secondary: {
      main: '#0f2a4f',
      light: '#35557d',
      contrastText: '#FFFFFF',
    },
    background: {
      default: '#eef4fd',
      paper: '#FFFFFF',
    },
    text: {
      primary: '#0f172a',
      secondary: '#5b6f8d',
    },
  },
  typography: {
    fontFamily: '"Segoe UI", "Tahoma", "Arial", sans-serif',
    h4: {
      fontWeight: 600,
    },
    h5: {
      fontWeight: 500,
    },
    button: {
      textTransform: 'none',
      fontWeight: 600,
    },
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: 999,
          padding: '10px 20px',
          fontWeight: 700,
        },
        containedPrimary: {
          background: 'linear-gradient(135deg, #0b4fa8, #1f63be)',
          boxShadow: '0 12px 24px rgba(11, 79, 168, 0.28)',
          '&:hover': {
            background: 'linear-gradient(135deg, #083a7a, #0b4fa8)',
          },
        },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: {
          background: 'rgba(255,255,255,0.95)',
          color: '#0b4fa8',
          borderBottom: '1px solid rgba(15,42,79,0.12)',
          boxShadow: '0 8px 24px rgba(15, 42, 79, 0.08)',
          backdropFilter: 'blur(8px)',
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          borderRadius: 14,
          border: '1px solid rgba(15,42,79,0.12)',
        },
      },
    },
    MuiTableContainer: {
      styleOverrides: {
        root: {
          overflowX: 'auto',
        },
      },
    },
    MuiTableCell: {
      styleOverrides: {
        root: {
          '@media (max-width:900px)': {
            padding: '8px 10px',
            fontSize: '0.78rem',
            whiteSpace: 'nowrap',
          },
        },
      },
    },
    MuiDialog: {
      styleOverrides: {
        paper: {
          '@media (max-width:900px)': {
            margin: 8,
            width: 'calc(100% - 16px)',
            maxWidth: 'calc(100% - 16px)',
          },
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: 16,
          boxShadow: '0 18px 36px rgba(15, 42, 79, 0.12)',
          border: '1px solid rgba(15, 42, 79, 0.12)',
        },
      },
    },
  },
});
