import { Box } from '@mui/material';
import QueryStatsRoundedIcon from '@mui/icons-material/QueryStatsRounded';

/** Gradient app logo mark, used in the login card and top bars. */
export default function BrandMark({ size = 28 }: { size?: number }) {
  return (
    <Box
      aria-hidden
      sx={{
        width: size,
        height: size,
        display: 'grid',
        placeItems: 'center',
        borderRadius: `${Math.round(size * 0.25)}px`,
        color: '#fff',
        background: 'linear-gradient(135deg, #4d8ef0 0%, #2f6fd0 100%)',
        boxShadow: '0 4px 14px rgba(77, 142, 240, 0.35)',
        flexShrink: 0,
      }}
    >
      <QueryStatsRoundedIcon sx={{ fontSize: size * 0.6 }} />
    </Box>
  );
}
