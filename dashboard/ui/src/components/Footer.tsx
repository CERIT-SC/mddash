import { AppBar, Toolbar, Typography } from "@mui/material";

const Footer = () => (
    <AppBar position="static" color="primary">
        <Toolbar>
            <Typography variant="body1" sx={{ flexGrow: 1, textAlign: "center" }}>
                TODO
            </Typography>
        </Toolbar>
    </AppBar>
);

export default Footer;
