import { Link } from "react-router-dom";
import { Box, Typography, Button, Paper } from "@mui/material";
import SentimentVeryDissatisfiedIcon from "@mui/icons-material/SentimentVeryDissatisfied";

import { BASE_PATH } from "@/util/const";

const NotFound = () => {
    return (
        <Box
            sx={{
                minHeight: "80vh",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
            }}
        >
            <Paper elevation={6} sx={{ p: 6, textAlign: "center", maxWidth: 400 }}>
                <SentimentVeryDissatisfiedIcon sx={{ fontSize: 80, mb: 2, color: "text.secondary" }} />
                <Typography variant="h1" gutterBottom>
                    404
                </Typography>
                <Typography variant="h4" gutterBottom>
                    Oops! This page wandered off...
                </Typography>
                <Typography variant="body2" sx={{ mb: 3 }}>
                    Looks like the page you're looking for got lost in cyberspace — maybe it's off chasing butterflies,
                    or just hiding from you!
                </Typography>
                <Button variant="contained" color="primary" component={Link} to={BASE_PATH}>
                    Take me home!
                </Button>
            </Paper>
        </Box>
    );
};

export default NotFound;
