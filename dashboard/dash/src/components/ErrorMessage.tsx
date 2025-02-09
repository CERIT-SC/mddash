import { Paper, Typography, useTheme, alpha } from '@mui/material';


interface ErrorMessageProps {
    message: string;
}

const ErrorMessage = (props: ErrorMessageProps) => {
    const { message } = props;

    const theme = useTheme();
    const transparentError = alpha(theme.palette.error.main, 0.4);

    return (
        <Paper elevation={2} sx={{ p: 2, backgroundColor: transparentError }}>
            <Typography variant="body1">
                {message}
            </Typography>
        </Paper>
    )
}

export default ErrorMessage;
