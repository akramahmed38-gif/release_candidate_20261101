import React from 'react';
import { Box, Button, Card, CardContent, CircularProgress, IconButton, Tooltip, Typography } from '@mui/material';
import { Delete, Edit } from '@mui/icons-material';

export const libraryCardGridSx = {
  display: 'grid',
  gridTemplateColumns: {
    xs: 'minmax(0, 1fr)',
    sm: 'repeat(auto-fill, 320px)',
  },
  justifyContent: 'start',
  gap: { xs: 2, md: 2.5 },
};

const actionClusterSx = {
  display: 'flex',
  alignItems: 'center',
  gap: 0.25,
  p: 0.25,
  border: '1px solid #e5e7eb',
  borderRadius: 99,
  bgcolor: '#f9fafb',
  '& .MuiIconButton-root': {
    width: 32,
    height: 32,
    borderRadius: '50%',
    color: '#4b5563',
    '&:hover': { bgcolor: '#e5e7eb' },
  },
  '& .MuiIconButton-colorError': {
    color: '#d32f2f',
    '&:hover': { bgcolor: 'rgba(211, 47, 47, 0.10)' },
  },
};

export default function LibraryItemCard({
  Icon,
  iconColor,
  iconBackground,
  name,
  secondaryLabel,
  secondaryText,
  ariaLabel,
  actionLabel,
  ActionIcon,
  onOpen,
  onEdit,
  onDelete,
  isAdmin,
  deletePending,
  openPending,
  editLabel,
  deleteLabel,
}) {
  const openItem = () => {
    if (!openPending) onOpen();
  };

  return (
    <Card
      tabIndex={0}
      aria-label={ariaLabel}
      onClick={openItem}
      onKeyDown={(event) => {
        if (event.currentTarget !== event.target || (event.key !== 'Enter' && event.key !== ' ')) return;
        event.preventDefault();
        openItem();
      }}
      sx={{
        width: { xs: '100%', sm: 320 },
        height: 232,
        display: 'flex',
        flexDirection: 'column',
        bgcolor: '#ffffff',
        border: '1px solid #dfe5ed',
        borderRadius: 4,
        boxShadow: '0 10px 26px rgba(15, 42, 79, 0.10)',
        cursor: openPending ? 'wait' : 'pointer',
        transition: 'transform 180ms ease, box-shadow 180ms ease, border-color 180ms ease',
        '&:hover': {
          transform: 'translateY(-3px)',
          borderColor: 'rgba(11, 79, 168, 0.24)',
          boxShadow: '0 18px 36px rgba(15, 42, 79, 0.16)',
        },
        '&:focus-visible': {
          outline: '3px solid rgba(11, 79, 168, 0.28)',
          outlineOffset: 2,
        },
      }}
    >
      <CardContent
        sx={{
          display: 'flex',
          flexDirection: 'column',
          height: '100%',
          p: 2.25,
          '&:last-child': { pb: 2.25 },
          gap: 1,
        }}
      >
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 1 }}>
          <Box
            sx={{
              width: 60,
              height: 60,
              flex: '0 0 auto',
              borderRadius: '50%',
              display: 'grid',
              placeItems: 'center',
              bgcolor: iconBackground,
              color: iconColor,
            }}
          >
            <Icon />
          </Box>

          {isAdmin ? (
            <Box sx={actionClusterSx} onClick={(event) => event.stopPropagation()}>
              <Tooltip title={editLabel}>
                <IconButton size="small" onClick={onEdit} aria-label={editLabel}>
                  <Edit fontSize="small" />
                </IconButton>
              </Tooltip>
              <Tooltip title={deleteLabel}>
                <span>
                  <IconButton size="small" color="error" disabled={deletePending} onClick={onDelete} aria-label={deleteLabel}>
                    {deletePending ? <CircularProgress size={16} color="inherit" /> : <Delete fontSize="small" />}
                  </IconButton>
                </span>
              </Tooltip>
            </Box>
          ) : null}
        </Box>

        <Tooltip title={name} placement="top-start">
          <Typography
            dir="auto"
            sx={{
              color: '#0b1f4d',
              fontSize: '0.98rem',
              fontWeight: 700,
              lineHeight: 1.42,
              minHeight: '2.84em',
              maxHeight: '2.84em',
              textAlign: 'start',
              wordBreak: 'break-word',
              display: '-webkit-box',
              WebkitBoxOrient: 'vertical',
              WebkitLineClamp: 2,
              overflow: 'hidden',
            }}
          >
            {name}
          </Typography>
        </Tooltip>

        {secondaryText ? (
          <Typography sx={{ color: '#6b7280', fontSize: '0.8rem', fontWeight: 600, lineHeight: 1.3 }}>
            {secondaryLabel ? `${secondaryLabel}: ${secondaryText}` : secondaryText}
          </Typography>
        ) : null}

        <Box sx={{ mt: 'auto' }}>
          <Button
            fullWidth
            variant="contained"
            startIcon={openPending ? <CircularProgress size={16} color="inherit" /> : <ActionIcon />}
            disabled={openPending}
            onClick={(event) => {
              event.stopPropagation();
              openItem();
            }}
            sx={{
              minHeight: 42,
              borderRadius: 2.5,
              color: '#102a56',
              fontWeight: 800,
              boxShadow: 'none',
              background: 'linear-gradient(135deg, #ffeba2 0%, #ffdb55 52%, #f4c500 100%)',
              '&:hover': {
                boxShadow: '0 7px 16px rgba(200, 155, 0, 0.28)',
                background: 'linear-gradient(135deg, #ffe57a 0%, #ffd200 52%, #e8b900 100%)',
              },
            }}
          >
            {actionLabel}
          </Button>
        </Box>
      </CardContent>
    </Card>
  );
}
