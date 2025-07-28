import { AppBar, Toolbar, Typography } from "@mui/material";

const Footer = () => (
    <AppBar position="static" color="primary" sx={{ top: "auto", bottom: 0, width: "100%" }}>
        <Toolbar>
            <Typography variant="caption" color="inherit" sx={{ flexGrow: 1, textAlign: "center" }}>
                TODO
            </Typography>
        </Toolbar>
    </AppBar>
);

export default Footer;
