/* chrome.identity.getAuthToken({ interactive: true }, function (token) {
    var newURL = "https://www.google.com/calendar/";
    chrome.tabs.create({ url: newURL });

    // newURL = "https://outlook.office365.com/calendar/";
    // chrome.tabs.create({ url: newURL });
}); */

chrome.identity.getAuthToken({ interactive: true }, function (token) {
    if (chrome.runtime.lastError) {
        console.log(chrome.runtime.lastError.message);
        return;
    }

    // You are now authenticated and can make authorized requests.
    getCalendarEvents(token);
});

function getCalendarEvents(token) {
    fetch("https://www.googleapis.com/calendar/v3/calendars/primary/events?access_token=${token}", {
        headers: {
            "Content-Type": "application/json",
        },
    })
    .then((response) => response.json())
    .then((data) => console.log("Data: ", data))
    .catch((error) => console.error("Error:", error));
}
 