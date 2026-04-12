import { ThemeProvider, createTheme, CssBaseline } from '@mui/material';
import BacktestPage from './pages/BacktestPage';
import ErrorBoundary from './components/ErrorBoundary';

const darkTheme = createTheme({
  palette: {
    mode: 'dark',
    background: {
      default: '#0d0f1a',
      paper: '#131929',
    },
    primary: {
      main: '#4d8ef0',
    },
    divider: '#1e2d45',
  },
});

export default function App() {
  return (
    <ThemeProvider theme={darkTheme}>
      <CssBaseline />
      <ErrorBoundary>
        <BacktestPage />
      </ErrorBoundary>
    </ThemeProvider>
  );
}
