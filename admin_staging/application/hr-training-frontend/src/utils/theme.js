import { alpha, createTheme } from '@mui/material/styles';

const brand = {
  yellow: '#FFD200',
  yellowDeep: '#E0B100',
  yellowSoft: '#FFF1A8',
  yellowWash: '#FFF9E7',
  surface: '#FFFCF6',
  paper: '#FFFFFF',
  navy: '#1F3558',
  navyDeep: '#17263D',
  ink: '#222B38',
  muted: '#667085',
  line: 'rgba(31, 53, 88, 0.12)',
  lineStrong: 'rgba(31, 53, 88, 0.18)',
  warning: '#A6691A',
  success: '#2E7D5B',
};

const motion = '220ms cubic-bezier(0.22, 1, 0.36, 1)';

export const theme = createTheme({
  shape: {
    borderRadius: 16,
  },
  palette: {
    primary: {
      main: brand.yellow,
      dark: brand.yellowDeep,
      light: '#FFE37A',
      contrastText: brand.navyDeep,
    },
    secondary: {
      main: brand.navy,
      dark: brand.navyDeep,
      light: '#355179',
      contrastText: '#FFFFFF',
    },
    success: {
      main: brand.success,
    },
    background: {
      default: brand.surface,
      paper: brand.paper,
    },
    text: {
      primary: brand.ink,
      secondary: brand.muted,
    },
    divider: brand.line,
  },
  typography: {
    fontFamily: '"Segoe UI", "Tahoma", "Arial", sans-serif',
    h4: {
      fontWeight: 800,
      letterSpacing: '-0.03em',
    },
    h5: {
      fontWeight: 700,
    },
    button: {
      textTransform: 'none',
      fontWeight: 700,
    },
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        body: {
          background:
            'radial-gradient(circle at top left, #fffdf6 0%, #fff8e2 26%, #f7f2e9 64%, #f3efe8 100%)',
          color: brand.ink,
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        startIcon: { marginLeft: 0, marginRight: 0, marginInlineEnd: 8, flexShrink: 0 },
        endIcon: { marginLeft: 0, marginRight: 0, marginInlineStart: 8, flexShrink: 0 },
        root: {
          columnGap: 8,
          '& .MuiButton-startIcon, & .MuiButton-endIcon': { margin: 0, flexShrink: 0 },
          borderRadius: 9999,
          padding: '10px 20px',
          fontWeight: 700,
          transition: `transform ${motion}, box-shadow ${motion}, background-color ${motion}, border-color ${motion}, color ${motion}`,
        },
        containedPrimary: {
          background: 'linear-gradient(135deg, #ffe37a 0%, #ffd200 48%, #e0b100 100%)',
          color: brand.navyDeep,
          boxShadow: '0 16px 32px rgba(176, 138, 0, 0.20)',
          '&:hover': {
            background: 'linear-gradient(135deg, #ffe99a 0%, #ffd200 46%, #d6ac00 100%)',
            transform: 'translateY(-1px)',
            boxShadow: '0 20px 38px rgba(176, 138, 0, 0.26)',
          },
        },
        outlinedPrimary: {
          borderColor: alpha(brand.navy, 0.18),
          color: brand.navy,
          backgroundColor: alpha('#ffffff', 0.84),
          '&:hover': {
            borderColor: alpha(brand.yellowDeep, 0.55),
            backgroundColor: brand.yellowWash,
            transform: 'translateY(-1px)',
          },
        },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: {
          background: brand.yellow,
          color: brand.navy,
          borderBottom: `1px solid ${alpha(brand.navy, 0.16)}`,
          boxShadow: '0 12px 28px rgba(31, 53, 88, 0.12)',
          backdropFilter: 'none',
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          borderRadius: 16,
          border: `1px solid ${brand.line}`,
        },
      },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: {
          borderRadius: 16,
          backgroundColor: alpha('#ffffff', 0.92),
          '&.Mui-focused': {
            boxShadow: `0 0 0 4px ${alpha(brand.yellow, 0.22)}`,
          },
          '&.Mui-focused .MuiOutlinedInput-notchedOutline': {
            borderColor: brand.yellowDeep,
          },
        },
        notchedOutline: {
          borderColor: brand.lineStrong,
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
          boxShadow: '0 18px 40px rgba(31, 53, 88, 0.10)',
          border: `1px solid ${brand.line}`,
          background: 'linear-gradient(180deg, rgba(255,255,255,0.98), rgba(255,252,246,0.96))',
          transition: `transform ${motion}, box-shadow ${motion}, border-color ${motion}`,
        },
      },
    },
  },
});
